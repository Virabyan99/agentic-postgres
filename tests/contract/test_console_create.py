"""A project created in the console: only the digest leaves, the token is shown at acceptance (CON-CREATE-001).

Session 46 (ADR 0291; D2864, D2865; rig 46a). `services/console/public/create.js`
imports nothing -- `app.js` passes it `call` (api.js) and `wait` (its waitFor)
-- so it runs here in Node 22 (`NODE_RUNTIME_IMAGE`, `--network none`) with a
stand-in for each that records every argument and the order of events. The
view's half -- the panel drawn from `accepted`, the refusal through `refusal`,
the overview's link and its route -- is read from `app.js` and `pages.json`.
"""

from __future__ import annotations

# ruff: noqa: E501 -- the embedded JavaScript drivers keep one statement per line.
import base64
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests.contract.test_image_contracts import LOCK, requires_docker

from agentic_postgres import REPO_ROOT

pytestmark = [pytest.mark.contract, pytest.mark.p0, pytest.mark.security, requires_docker]

PUBLIC = REPO_ROOT / "services" / "console" / "public"
MODELS = REPO_ROOT / "services" / "auth-api" / "app" / "models.py"
NODE = LOCK["NODE_RUNTIME_IMAGE"]
ORG = "0b5c6f0e-8d0e-4c3a-9a4e-3f1d2b7c9e11"
OPERATION = "6f1d2b7c-9e11-4c3a-9a4e-0b5c6f0e8d0e"
TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def _node(tmp_path: Path, driver: str) -> Any:
    directory = tmp_path / "console"
    directory.mkdir(parents=True)
    for script in PUBLIC.glob("*.js"):
        shutil.copy(script, directory / script.name)
    (directory / "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
    (directory / "driver.js").write_text(driver, encoding="utf-8")
    done = subprocess.run(
        ["docker", "run", "--rm", "--network", "none", "-v", f"{directory}:/console:ro", NODE,
         "node", "/console/driver.js"],
        capture_output=True, text=True, check=False, timeout=120,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-3000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


#: A recording `call` and `wait`, and the order every event happened in.
#: `RUN` names `createProject` and leaves its import to the driver.
IMPORT = 'import { createProject } from "/console/create.js";\n'
RUN = r"""
const run = async (refuse) => {
  const seen = { calls: [], events: [], tokens: [], operations: [], waited: [] };
  const thrown = { status: 409, code: "plan_limit_reached", body: { error: "plan_limit_reached" } };
  const call = async (...args) => {
    seen.calls.push(args);
    seen.events.push("call");
    if (refuse) { throw thrown; }
    return { operation: { id: "OPERATION", status: "pending", project_key: null } };
  };
  const wait = async (id) => { seen.events.push("wait"); seen.waited.push(id); return { id, status: "succeeded", project_key: "slot10-prod" }; };
  const accepted = (token, operation) => { seen.events.push("accepted"); seen.tokens.push(token); seen.operations.push(operation); };
  try {
    seen.final = await createProject({ call, wait, accepted, organization: "ORG", name: "Shop backend", profile: "small", adminUsername: "shop.admin" });
  } catch (error) {
    seen.rejected = error === thrown ? "the server's own" : String(error);
  }
  return seen;
};
""".replace("OPERATION", OPERATION).replace("ORG", ORG)
STANDINS = IMPORT + RUN


def _view(name: str) -> str:
    """One function of `app.js`, from its `function` line to the next top-level one."""
    text = (PUBLIC / "app.js").read_text(encoding="utf-8")
    found = re.search(
        rf"^(async )?function {name}\(.*?(?=^(async )?function |\Z)", text, re.M | re.S
    )
    assert found, f"app.js has no function {name}"
    return found.group(0)


def test_only_the_digest_is_sent(tmp_path: Path) -> None:
    """ADR 0291 §2: ONE call, `POST /projects`, whose body is exactly the five
    members the server takes (`CreateProjectRequest`) and whose
    `handoff_sha256` is the SHA-256 hex of the token's UTF-8 -- computed here
    by Python's hashlib, the CLI's rule. The token is 43 base64url characters
    of 32 random bytes, two creations make two tokens, and the token appears in
    nothing sent."""
    out = _node(
        tmp_path, STANDINS + "console.log(JSON.stringify([await run(false), await run(false)]));\n"
    )
    tokens = []
    for seen in out:
        ((method, path, body),) = seen["calls"]
        (token,) = seen["tokens"]
        assert (method, path) == ("POST", "/projects")
        assert set(body) == {"organization", "name", "profile", "admin_username", "handoff_sha256"}
        assert body["organization"] == ORG and body["admin_username"] == "shop.admin"
        assert body["handoff_sha256"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert TOKEN_SHAPE.match(token), token
        assert len(base64.urlsafe_b64decode(token + "=")) == 32
        assert token not in json.dumps(seen["calls"]), "the token was sent"
        tokens.append(token)
    assert tokens[0] != tokens[1], "two creations made one token"


def test_the_token_is_shown_once_at_acceptance(tmp_path: Path) -> None:
    """ADR 0291 §3: `accepted` is called once with the token and the recorded
    operation the moment the server answers, BEFORE the wait -- the order of
    events is call, accepted, wait -- and the wait follows that operation.
    The view draws the token from `accepted` alone, into `tokenPanel` (the
    shown-once panel, `once`), with the claim line behind a disclosure marked
    optional and an *I've saved it, or I don't need it* that REPLACES the panel
    -- the token with it -- by a one-line record (ADR 0291 amended at Session
    47 Run 5; ADR 0296 decision 6). On acceptance the address becomes the
    creation's tracker, the wait is the tracker's reader, and the link to
    Connect -- with the optional claim line, key filled -- comes from the
    finished operation's key; after a refresh the tracker says the token was
    shown once and is not needed to connect."""
    out = _node(tmp_path, STANDINS + "console.log(JSON.stringify(await run(false)));\n")
    assert out["events"] == ["call", "accepted", "wait"], out["events"]
    assert out["operations"] == [{"id": OPERATION, "status": "pending", "project_key": None}]
    assert out["waited"] == [OPERATION]
    assert out["final"]["project_key"] == "slot10-prod"

    view = _view("newProjectView")
    accepted = view[view.index("accepted:") : view.index("organization:")]
    assert "tokenPanel(token, " in accepted, accepted
    assert 'history.pushState(null, "", `#/operations/${operation.id}`);' in accepted
    assert "wait: (id) => follow(id, turn, parts, null)," in view
    assert view.count("token") == accepted.count("token"), "the token is used outside the panel"
    panel = _view("tokenPanel")
    assert 'once("The handoff token:", token)' in panel and "CLAIM_SENTENCE" in panel
    assert '"Using it from a terminal (optional)"' in panel and "claimLine(null)" in panel
    assert '"You do not need it to connect"' in panel and "It is shown once" in panel
    assert "button(\"I've saved it, or I don't need it\", () => panel.replaceWith(" in panel
    record = panel[panel.index("panel.replaceWith(") : panel.index("return panel;")]
    assert not re.search(r"[(,]\s*token\b", record), "the one-line record holds the token"
    assert "panel.remove()" not in panel and '"I have saved it"' not in view
    onward = _view("onward")
    assert "#/projects/${key}/connect" in onward and "claimLine(key)" in onward
    assert '"Connect to it"' in onward
    tracker = _view("trackerParts")
    assert 'row.type === "project.create" && !shownHere' in tracker
    assert "You do not need it to connect." in tracker


def test_no_storage_is_touched(tmp_path: Path) -> None:
    """ADR 0291 §4: a creation writes no storage. Every store a browser has is
    a recording stand-in, and a whole creation and a refused one touch none.
    The control: the recorder records a planted access."""
    # The stores are planted BEFORE the module loads, so a dynamic import.
    driver = (
        r"""
const touched = [];
const store = (name) => new Proxy({}, { get: (_, p) => { touched.push(name + "." + String(p)); return () => null; }, set: (_, p) => { touched.push(name + "=" + String(p)); return true; } });
for (const name of ["localStorage", "sessionStorage", "indexedDB", "caches"]) { globalThis[name] = store(name); }
globalThis.document = { get cookie() { touched.push("cookie"); return ""; }, set cookie(v) { touched.push("cookie="); } };
const { createProject } = await import("/console/create.js");
"""
        + RUN
        + r"""
await run(false);
await run(true);
const clean = touched.length;
localStorage.setItem("planted", "x");
console.log(JSON.stringify({ clean, planted: touched }));
"""
    )
    out = _node(tmp_path, driver)
    assert out["clean"] == 0, out["planted"]
    assert out["planted"] == ["localStorage.setItem"]
    for name in ("create.js", "app.js", "nav.js", "ui.js", "messages.js", "progress.js"):
        text = (PUBLIC / name).read_text(encoding="utf-8")
        for store in ("localStorage", "sessionStorage", "indexedDB", "document.cookie", "caches."):
            assert store not in text, f"{name} touches {store}"


def test_a_refusal_is_the_servers(tmp_path: Path) -> None:
    """ADR 0291 §1: a refused creation rejects with the server's OWN error,
    unchanged, and neither shows a token nor waits -- nothing was recorded, so
    there is nothing to save. The view renders it through `refusal`, which
    gives the code and the documented sentence for each refusal the route
    names."""
    out = _node(tmp_path, STANDINS + "console.log(JSON.stringify(await run(true)));\n")
    assert out["rejected"] == "the server's own", out.get("rejected")
    assert out["events"] == ["call"] and out["tokens"] == [] and out["waited"] == []

    view = _view("newProjectView")
    assert "catch (error)" in view and "refusal(error, { organization: org })" in view
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    # Since Session 47 Run 6 (D3012) the editor's close words come from there too.
    assert (
        'import { closeSentence, refusal, said, sentence, SESSION_LIMITS } from "/console/messages.js";'
        in app
    )
    # Since Session 47 (ADR 0295 decision 3, ADR 0297) the words live in messages.js.
    words = (PUBLIC / "messages.js").read_text(encoding="utf-8")
    refusals = words[
        words.index("const REFUSALS") : words.index("};", words.index("const REFUSALS"))
    ]
    for code in ("plan_limit_reached", "capacity_exhausted", "conflict", "not_available"):
        assert f"  {code}:" in refusals, code


def test_the_overview_offers_new_project() -> None:
    """D2864: the overview's CLI sentence is gone and each organisation where
    the caller is a member or above links its *New project* view, a route of
    the router and a view of `pages.json` calling exactly the creation and the
    operation it follows. The name field is as long as the server's pattern
    allows (`CreateProjectRequest.name`, read from models.py)."""
    app = (PUBLIC / "app.js").read_text(encoding="utf-8")
    assert "command-line client in this beta" not in app
    # Since Session 47 Run 5 (D2951, ADR 0297 decision 6) the action is one
    # helper the Projects pages share: the link, or a disabled button while a
    # creation is open or the plan is full; each organisation's section on the
    # overview draws it.
    action = _view("newProjectAction")
    assert "#/org/${organization.id}/new-project" in action and '"New project"' in action
    assert '["owner", "admin", "member"].includes(organization.role)' in action
    assert "disabled: true" in action
    assert "newProjectAction(organization, blocked, reading.plan)" in _view("organizationSection")
    assert "organizationSection(organization, readings[index])" in _view("overview")
    assert "[/^#\\/org\\/([^/]+)\\/new-project$/, newProjectView, UUID]," in app
    pages = json.loads((PUBLIC / "pages.json").read_text(encoding="utf-8"))["views"]
    (view,) = [v for v in pages if v["id"] == "new-project"]
    assert view["path"] == "/console/#/org/{organization}/new-project"
    # The creation and the operation it follows; since Session 47 Run 5 the
    # plan and the open creations that refuse the form before it is filled.
    assert view["calls"] == [
        "POST /v1/projects",
        "GET /v1/operations/{operation}",
        "GET /v1/organizations/{organization}/plan",
        "GET /v1/operations",
    ]
    assert view["ledger"] == ["projects_self_service"]
    longest = re.search(
        r"name: str = Field\(pattern=r\"\^\[A-Za-z0-9 \._-\]\{1,(\d+)\}\$\"\)",
        MODELS.read_text("utf-8"),
    )
    assert longest, "CreateProjectRequest.name's pattern moved"
    assert f'field("Name", {{ maxLength: {longest.group(1)} }}, ' in _view("newProjectView")

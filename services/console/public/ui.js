// The console's components (ADR 0295 decision 6), each built once. Every
// value is set as text or a DOM property, never parsed as markup; an icon is
// static markup in a page's <template>, cloned here, never built by script.
//
// What this file holds: `h` and the building blocks every view uses; the one
// aria-live region of the page, written by `announce`; the copy button
// (Copied for two seconds, announced once, the text selected instead when the
// clipboard refuses); the busy button (disabled and relabelled while its work
// runs, so a second click sends nothing); the code block, which always carries
// a copy button; the shown-once panel; the state chip (ADR 0288's STATE_CHIPS,
// unchanged); callout, banner, empty state, skeleton, toast and tabs; and the
// site's origin, derived from this page's host, never typed. Since Session 47
// Run 5: a time as words (`when`, D3007).

import { absoluteTime, machineTime, relativeAge } from "/console/progress.js";

// One element, its properties and its children -- strings become text nodes.
// A property whose name holds a dash (`aria-selected`, `data-x`) is an
// attribute. Children are flattened to any depth: a component hands its
// children on as one list, and a list printed as text would read
// "[object HTMLElement]" (D2713).
export function h(tag, properties, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(properties || {})) {
    if (name.startsWith("on")) {
      element.addEventListener(name.slice(2), value);
    } else if (name.includes("-")) {
      element.setAttribute(name, String(value));
    } else {
      element[name] = value;
    }
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) {
      element.append(typeof child === "string" || typeof child === "number" ? document.createTextNode(String(child)) : child);
    }
  }
  return element;
}

export function value(text) {
  return text === null || text === undefined ? "—" : String(text);
}

// A time the server served, as a person reads it (D3007): by default the
// relative age ("14 min ago") with the absolute local time as its title;
// `absolute` shows the local time with the age as its title. The machine form
// is the element's `datetime`. A missing time is the dash; one that is not a
// time is said to be unreadable, never printed raw.
export function when(at, style) {
  if (at === null || at === undefined) {
    return h("span", {}, "—");
  }
  const machine = machineTime(at);
  if (machine === null) {
    return h("span", {}, "an unreadable time");
  }
  const relative = relativeAge(at, Date.now());
  const absolute = absoluteTime(at);
  return style === "absolute"
    ? h("time", { dateTime: machine, title: relative }, absolute)
    : h("time", { dateTime: machine, title: absolute }, relative);
}

// -- the site, derived from this page's host -----------------------------------

// The console is served at `control.<domain>` and the site at `<domain>`, so
// the site's name is this host's minus its first label (ADR 0298). A host with
// no such label -- an address, `localhost` -- is its own.
export function siteDomain() {
  const labels = location.hostname.split(".");
  const address = /^[0-9]+$/.test(labels[labels.length - 1]);
  return labels.length > 2 && !address ? labels.slice(1).join(".") : location.hostname;
}

export function siteLink(path) {
  return `https://${siteDomain()}${path}`;
}

// -- the page's one live region ------------------------------------------------

const live = h("p", { className: "sr", "aria-live": "polite" });
const toasts = h("div", { className: "toasts" });
document.body.append(live, toasts);

// Said once to a screen reader: the region is emptied first, so the same word
// twice is announced twice.
export function announce(text) {
  live.textContent = "";
  setTimeout(() => { live.textContent = text; }, 50);
}

// A short note in the corner for three seconds, announced as it appears.
export function toast(text) {
  const note = h("div", { className: "toast" }, text);
  toasts.append(note);
  announce(text);
  setTimeout(() => note.remove(), 3000);
}

// -- icons, cloned from a page's static <template> ------------------------------

export function icon(name) {
  const template = document.getElementById(name);
  return template && template.content.firstElementChild ? template.content.firstElementChild.cloneNode(true) : null;
}

// -- controls --------------------------------------------------------------------

// A labelled input. A hint is OUTSIDE the label, tied to the input by
// `aria-describedby`, so the field's accessible name stays its label alone.
let hints = 0;

export function field(label, properties, hint) {
  if (!hint) {
    const input = h("input", properties);
    return [h("label", {}, label, input), input];
  }
  hints += 1;
  const id = `hint-${hints}`;
  const input = h("input", { ...properties, "aria-describedby": id });
  return [h("div", { className: "field" }, h("label", {}, label, input), h("p", { className: "hint", id }, hint)), input];
}

function options(list, selected) {
  return list.map((option) => h("option", { value: option.value ?? option, selected: (option.value ?? option) === selected }, option.label ?? option));
}

export function choice(label, list, selected) {
  const select = h("select", {}, options(list, selected));
  return [h("label", {}, label, select), select];
}

// A choice inside a table row, whose column head is its visible label: named
// for a screen reader by its row ("Role of example-owner"), never unnamed.
export function cellChoice(name, list, selected) {
  return h("select", { "aria-label": name }, options(list, selected));
}

export function button(text, onclick, properties) {
  return h("button", { type: "button", onclick, ...(properties || {}) }, text);
}

// The current view's link is marked for the eye and for a screen reader (ADR 0288).
export function link(route, text) {
  return h("a", location.hash === route ? { href: route, ariaCurrent: "page" } : { href: route }, text);
}

// A button whose work is a promise: while it runs the button is disabled and
// says what it is doing, so a second click sends nothing (D2955). `enabled`,
// when given, says whether the button may be pressed once its work is done
// (the editor's Cancel: only while a statement runs).
export function busyButton(text, work, options) {
  const { busy, enabled, ...properties } = options || {};
  const element = h("button", { type: "button", ...properties }, text);
  element.addEventListener("click", async (event) => {
    if (element.disabled) {
      return;
    }
    element.disabled = true;
    element.setAttribute("aria-busy", "true");
    element.replaceChildren(h("span", { className: "spinner", "aria-hidden": "true" }), busy || "Working…");
    try {
      await work(event);
    } finally {
      element.disabled = enabled ? !enabled() : false;
      element.removeAttribute("aria-busy");
      element.replaceChildren(text);
    }
  });
  return element;
}

// Selects a node's text, for a person to copy when the clipboard refused.
function select(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

// Copies `text`; reads "Copied" for two seconds and says it once. If the
// browser refuses the clipboard, `target`'s text is selected instead.
export function copyButton(text, options) {
  const { label = "Copy", target = null } = options || {};
  const words = h("span", {}, label);
  const element = h("button", { type: "button", className: "copy" }, icon("i-copy"), words);
  let timer = null;
  element.addEventListener("click", async () => {
    try {
      if (!navigator.clipboard) {
        throw new Error("no clipboard");
      }
      await navigator.clipboard.writeText(text);
    } catch (error) {
      if (target) {
        select(target);
      }
      announce("The browser did not allow copying. The text is highlighted: copy it with your keyboard.");
      return;
    }
    words.textContent = "Copied";
    element.classList.add("copied");
    announce("Copied");
    clearTimeout(timer);
    timer = setTimeout(() => {
      words.textContent = label;
      element.classList.remove("copied");
    }, 2000);
  });
  return element;
}

// A value on one line with its copy button.
export function inlineCopy(text, className) {
  const code = h("code", className ? { className } : {}, text);
  return h("span", { className: "inline-copy" }, code, copyButton(text, { target: code }));
}

// A block of code to copy: a label, the copy button, the text. `secret` marks
// the code element as a value shown once (the walk drivers read it).
export function codeBlock(text, options) {
  const { label = "", secret = false } = options || {};
  const code = h("code", secret ? { className: "secret" } : {}, text);
  return h("div", { className: "code" },
    h("div", { className: "code-head" }, h("span", {}, label), copyButton(text, { target: code })),
    h("pre", {}, code));
}

// A secret, shown once: in a <code> element with a Copy button. It lives in
// this element only, and is gone when the view is left.
export function once(label, secret) {
  const code = h("code", { className: "secret" }, secret);
  return h("div", { className: "once" },
    h("p", {}, label, h("strong", {}, " Shown once — copy it now.")),
    h("span", { className: "inline-copy" }, code, copyButton(secret, { target: code })));
}

// -- state ---------------------------------------------------------------------

// A project's or a branch's state as a chip (ADR 0288, D2827): the state word
// unchanged, its colour by class. Any value this table does not name -- or that
// is only a property of every object -- reads as unknown, never as ready
// (ADR 0195).
export const STATE_CHIPS = {
  ready: "state-ready",
  creating: "state-busy",
  starting: "state-busy",
  updating: "state-busy",
  suspending: "state-busy",
  deleting: "state-busy",
  sleeping: "state-asleep",
  deleted: "state-gone",
  unknown: "state-unknown",
};

export function stateChip(state) {
  const known = typeof state === "string" && Object.hasOwn(STATE_CHIPS, state);
  return h("span", { className: "chip " + (known ? STATE_CHIPS[state] : "state-unknown") }, value(state));
}

// -- surfaces --------------------------------------------------------------------

// `numeric` names the columns whose cells are right-aligned figures (ADR 0288).
export function table(columns, rows, numeric) {
  const cell = (name) => (numeric && numeric.has(name) ? { className: "num" } : {});
  return h("div", { className: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, columns.map(([name, title]) => h("th", { scope: "col", ...cell(name) }, title)))),
    h("tbody", {}, rows.map((row) => h("tr", {}, columns.map(([name]) => h("td", cell(name), row[name] instanceof Node ? row[name] : value(row[name]))))))));
}

export function card(...children) {
  return h("section", { className: "card" }, children);
}

// An explanation or a warning, with its actions under it.
export function callout(kind, title, ...children) {
  return h("div", { className: "callout " + kind }, title ? h("h3", {}, title) : null, children);
}

// One per page, at its top: a limit near or reached, with its link.
export function banner(...children) {
  return h("div", { className: "banner" }, h("p", {}, children));
}

// Nothing to show, and the next thing to do.
export function emptyState(sentence, action) {
  return h("div", { className: "empty" }, h("p", {}, sentence), action || null);
}

// The page's own shape while it waits -- never a blank page, never "Loading".
export function skeleton() {
  return h("div", { className: "skeleton", "aria-hidden": "true" },
    h("div", { className: "sk w60" }), h("div", { className: "sk h" }), h("div", { className: "sk" }),
    h("div", { className: "sk block" }));
}

// Tabs with tab semantics: `items` is [{label, panel}], one panel shown. Each
// tab controls its panel and each panel is labelled by its tab; the arrow
// keys, Home and End move between tabs; `name` labels the tab list.
let tabSets = 0;

export function tabs(items, name) {
  tabSets += 1;
  const id = (kind, index) => `tabs-${tabSets}-${kind}-${index}`;
  const buttons = [];
  const panels = items.map((item, index) => h("div", {
    role: "tabpanel", id: id("panel", index), tabIndex: 0, "aria-labelledby": id("tab", index),
  }, item.panel));
  const choose = (index) => {
    buttons.forEach((tab, at) => {
      tab.setAttribute("aria-selected", String(at === index));
      tab.tabIndex = at === index ? 0 : -1;
      panels[at].hidden = at !== index;
    });
  };
  items.forEach((item, index) => {
    buttons.push(h("button", {
      type: "button", role: "tab", id: id("tab", index), "aria-controls": id("panel", index),
      onclick: () => choose(index),
      onkeydown: (event) => {
        const last = items.length - 1;
        const moves = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last };
        if (Object.hasOwn(moves, event.key)) {
          event.preventDefault();
          choose(moves[event.key]);
          buttons[moves[event.key]].focus();
        }
      },
    }, item.label));
  });
  choose(0);
  const list = h("div", { className: "tablist", role: "tablist", ...(name ? { "aria-label": name } : {}) }, buttons);
  return h("div", { className: "tabs" }, list, panels);
}

// A long operation's progress, in words (ADR 0296): DOM-free, so Node can drive
// it (tests/contract/test_console_progress.py). It imports nothing and keeps
// nothing; every answer is computed from the operation the API served -- its
// `status`, `step`, `steps` ([{step, started_at}], when each step first began)
// and `expected` ({steps: [{step, label, typical_seconds}], typical_seconds:
// {low, high}, bound_seconds}, the server's `operation_steps`) -- and the time
// `now` (milliseconds, the browser's clock). An elapsed time is the browser's
// clock against the server's, so the page says "about". A value the operation
// does not carry is `null`, never 0 (ADR 0195).
//
// Since Session 47 Run 5 it also words every time a page draws (D3007: a
// relative age, the absolute local time beside it -- never the server's ISO
// text), decides whether a new project may start (D2951), and derives the
// getting-started checklist from API readings alone (ADR 0298 decision 4).
// Since Run 9b: whether a destructive action's name was typed (D3088), and
// usage in words and human units (D3090).

export const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

// The four words a step can be in: done, the one running now, where a failed
// or cancelled operation stopped, and the ones not reached.
export const DONE = "done";
export const CURRENT = "current";
export const STOPPED = "stopped";
export const TO_COME = "to come";

// "45 s", "14 min", "1 h 5 min"; null for anything that is not a duration.
export function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) {
    return null;
  }
  const whole = Math.round(seconds);
  if (whole < 60) {
    return `${whole} s`;
  }
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

function instant(at) {
  if (typeof at === "number") {
    return Number.isFinite(at) ? at : null;
  }
  if (typeof at !== "string") {
    return null;
  }
  const parsed = Date.parse(at);
  return Number.isNaN(parsed) ? null : parsed;
}

// Seconds from `since` (an ISO time) to `until` (an ISO time or milliseconds):
// null when either cannot be read; 0 when the browser's clock is behind.
export function elapsedSeconds(since, until) {
  const from = instant(since);
  const to = instant(until);
  if (from === null || to === null) {
    return null;
  }
  return Math.max(0, (to - from) / 1000);
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

// The typical time as words: "about 23 to 28 minutes", "about 20 seconds".
// From the served range only; null when the operation carries none.
export function typicalRange(expected) {
  const range = expected && expected.typical_seconds;
  if (!range || typeof range.low !== "number" || typeof range.high !== "number") {
    return null;
  }
  const [low, high] = [Math.min(range.low, range.high), Math.max(range.low, range.high)];
  if (high < 90) {
    const [from, to] = [Math.max(1, Math.round(low)), Math.max(1, Math.round(high))];
    return from === to ? `about ${plural(from, "second")}` : `about ${from} to ${to} seconds`;
  }
  const [from, to] = [Math.max(1, Math.round(low / 60)), Math.max(1, Math.round(high / 60))];
  return from === to ? `about ${plural(from, "minute")}` : `about ${from} to ${to} minutes`;
}

// The server's bound on the whole operation, as words: "30 minutes".
export function limitText(expected) {
  const bound = expected && expected.bound_seconds;
  if (typeof bound !== "number" || !Number.isFinite(bound) || bound <= 0) {
    return null;
  }
  return plural(Math.round(bound / 60), "minute");
}

// How long the whole operation has run: from when it started (or was
// recorded) to when it finished, or to `now` while it runs.
export function operationSeconds(operation, now) {
  const since = operation.started_at || operation.created_at;
  return elapsedSeconds(since, operation.finished_at || now);
}

// Where the operation is among its expected steps: the step it names, or the
// furthest expected step its log has begun; -1 when it has begun none.
function position(names, operation, log) {
  const named = names.indexOf(operation.step);
  if (named >= 0) {
    return named;
  }
  let furthest = -1;
  for (const entry of log) {
    furthest = Math.max(furthest, names.indexOf(entry && entry.step));
  }
  return furthest;
}

// Each expected step with its state, when it began, and how long it took (or
// has taken so far). An operation whose type the server does not describe
// (`expected` null) has no steps to show: [].
export function stepStates(operation, now) {
  const expected = operation.expected && Array.isArray(operation.expected.steps) ? operation.expected.steps : [];
  const log = Array.isArray(operation.steps) ? operation.steps : [];
  const names = expected.map((step) => step.step);
  const began = new Map(log.filter((entry) => entry && typeof entry.step === "string").map((entry) => [entry.step, entry.started_at]));
  const at = position(names, operation, log);
  const status = operation.status;
  return expected.map((step, index) => {
    let state;
    if (status === "succeeded") {
      state = DONE;
    } else if (at < 0 || index > at) {
      state = TO_COME;
    } else if (index < at) {
      state = DONE;
    } else {
      state = status === "failed" || status === "cancelled" ? STOPPED : CURRENT;
    }
    const startedAt = began.has(step.step) ? began.get(step.step) : null;
    let until = null;
    if (state === DONE) {
      const later = names.slice(index + 1).find((name) => began.has(name));
      until = later ? began.get(later) : operation.finished_at || null;
    } else if (state === CURRENT) {
      until = now;
    } else if (state === STOPPED) {
      until = operation.finished_at || null;
    }
    return {
      step: step.step,
      label: step.label,
      state,
      started_at: startedAt,
      seconds: startedAt === null || until === null ? null : elapsedSeconds(startedAt, until),
      typical_seconds: typeof step.typical_seconds === "number" ? step.typical_seconds : null,
    };
  });
}

// One line for a status: what it is doing, for how long, and how long it
// usually takes -- never a percentage (ADR 0296 decision 5).
export function describe(operation, now) {
  const states = stepStates(operation, now);
  const running = states.findIndex((step) => step.state === CURRENT);
  const elapsed = formatDuration(operationSeconds(operation, now));
  const typical = typicalRange(operation.expected);
  if (TERMINAL.has(operation.status)) {
    return `Operation ${operation.status}` + (elapsed ? `, after about ${elapsed}.` : ".");
  }
  const doing = running >= 0
    ? `${states[running].label} (step ${running + 1} of ${states.length})`
    : operation.step ? `Operation ${operation.status}, ${operation.step}` : `Operation ${operation.status}`;
  return doing + (elapsed ? `, about ${elapsed} so far` : "") + (typical ? `; usually ${typical}.` : ".");
}

// -- times, in words (D3007) ------------------------------------------------------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "14 min ago", "3 h ago", "2 days ago", "just now"; a time ahead of `now`
// (an expiry) reads "in 14 min". From the browser's clock against the
// server's time, so it is a rough age; null when `at` is not a time.
export function relativeAge(at, now) {
  const then = instant(at);
  const clock = instant(now);
  if (then === null || clock === null) {
    return null;
  }
  const seconds = (clock - then) / 1000;
  const ahead = seconds < 0;
  const size = Math.abs(seconds);
  if (size < 45) {
    return ahead ? "in a moment" : "just now";
  }
  let words;
  if (size < 3600) {
    words = `${Math.max(1, Math.round(size / 60))} min`;
  } else if (size < 86400) {
    words = `${Math.floor(size / 3600)} h`;
  } else {
    words = plural(Math.floor(size / 86400), "day");
  }
  return ahead ? `in ${words}` : `${words} ago`;
}

// The absolute time in the browser's own time zone: "29 Oct 2026, 14:13".
// null when `at` is not a time.
export function absoluteTime(at) {
  const then = instant(at);
  if (then === null) {
    return null;
  }
  const date = new Date(then);
  const two = (number) => String(number).padStart(2, "0");
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}, ${two(date.getHours())}:${two(date.getMinutes())}`;
}

// The machine form for a <time datetime>, from the same instant; null when
// `at` is not a time.
export function machineTime(at) {
  const then = instant(at);
  return then === null ? null : new Date(then).toISOString();
}

// -- may a new project start? (D2951, ADR 0297 decision 6) -------------------------

// Null when it may; otherwise why not: a creation of the organisation's is
// still open (its name), or the plan's projects are all held. `creating` is
// the open creations (null when they could not be read) and `plan` the
// organisation's plan document (null when unread). What could not be read
// blocks nothing: the server decides, and its refusal is worded.
export function creationBlocked({ creating, plan }) {
  const open = Array.isArray(creating) ? creating : [];
  const counted = plan && plan.projects_active;
  const held = counted && typeof counted.held === "number" ? counted.held : null;
  const limit = counted && typeof counted.limit === "number" ? counted.limit : null;
  if (open.length) {
    const subject = open[0].subject || {};
    return { reason: "creating", name: typeof subject.name === "string" ? subject.name : null, operation: open[0].id || null, held, limit };
  }
  if (held !== null && limit !== null && held >= limit) {
    return { reason: "limit", name: null, operation: null, held, limit };
  }
  return null;
}

// -- the getting-started checklist (ADR 0298 decision 4) -------------------------

export const NOT_YET = "not yet";
export const NOT_READ = "not read";
// D3076 (Session 47 Run 9): a second factor the person's role does not need --
// a step they cannot take is not theirs, so it counts as done for hiding the card.
export const NOT_NEEDED = "not required";

// Lists read one per organisation, each an array or null when that reading
// failed: what was found, and whether any could not be read.
function gathered(lists) {
  const all = Array.isArray(lists) ? lists : [null];
  return {
    items: all.filter(Array.isArray).flat(),
    unread: all.some((list) => !Array.isArray(list)),
  };
}

function found(items, unread) {
  if (items.length) {
    return DONE;
  }
  return unread ? NOT_READ : NOT_YET;
}

// The five steps from an invitation to a connected application, each `done`,
// `current` (a project being created), `not yet`, or `not read` -- a reading
// the console could not make is said, never counted either way. Every input
// is what the API served: `me` (`GET /v1/me`, null when unread),
// `organizations` (the list, or null), and per organisation `projects`,
// `creating` (its open creations), `operations` (all of them) and `usage`
// (`GET .../usage`'s project documents), each an array or null. Nothing is
// remembered between calls.
export function checklist({ me, organizations, projects, creating, operations, usage }) {
  const factor = me && me.second_factor && typeof me.second_factor.enabled === "boolean"
    ? (me.second_factor.enabled ? DONE : me.second_factor.required === false ? NOT_NEEDED : NOT_YET)
    : NOT_READ;
  const organization = Array.isArray(organizations) ? (organizations.length ? DONE : NOT_YET) : NOT_READ;
  const held = gathered(projects);
  const open = gathered(creating);
  let project = found(held.items, held.unread);
  if (project !== DONE && open.items.length) {
    project = CURRENT;
  } else if (project === NOT_YET && open.unread) {
    project = NOT_READ;
  }
  const history = gathered(operations);
  const made = history.items.filter((operation) => operation && operation.type === "credential.rotate" && operation.status === "succeeded");
  const password = found(made, history.unread);
  const read = gathered(usage);
  const seen = read.items.filter((served) => {
    const figure = served && served.status === "read" && served.figures ? served.figures.customer_connections : null;
    return Boolean(figure) && ((typeof figure.max === "number" && figure.max > 0) || (typeof figure.latest === "number" && figure.latest > 0));
  });
  const unreadUsage = read.unread || read.items.some((served) => !served || served.status !== "read");
  let connection = NOT_YET;
  if (seen.length) {
    connection = DONE;
  } else if (!held.items.length) {
    connection = held.unread ? NOT_READ : NOT_YET;
  } else if (unreadUsage) {
    connection = NOT_READ;
  }
  return [
    { item: "factor", state: factor },
    { item: "organization", state: organization },
    { item: "project", state: project },
    { item: "password", state: password },
    { item: "connection", state: connection },
  ];
}

// The card is gone when every step is done -- a step the person's role does
// not need counts as done (D3076).
export function checklistComplete(states) {
  return Array.isArray(states) && states.length > 0 && states.every((entry) => entry.state === DONE || entry.state === NOT_NEEDED);
}

// -- a restore time (D3013) -----------------------------------------------------

// A `datetime-local` value -- the browser's own wall-clock time, with no zone
// -- as the instant the API takes (RFC 3339, UTC, `...Z`): ECMA-262 reads a
// date-time with no offset as local time. Null when it is empty or not one.
export function instantOf(local) {
  if (typeof local !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,3})?)?$/.test(local)) {
    return null;
  }
  const at = new Date(local);
  return Number.isNaN(at.getTime()) ? null : at.toISOString();
}

// The browser's time zone, by name ("Europe/Paris"), or null when it says none.
export function zoneName() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
  } catch (error) {
    return null;
  }
}

// -- a plan's entitlements in plain words (D3078) -------------------------------

// What a person calls each entitlement the plans serve (`GET /v1/plans`, the
// release's `plans.PLANS`), and the unit its number is said in. A name this
// table does not hold is said by its served unit -- never by its key.
const ENTITLEMENT_WORDS = {
  projects_active: { title: "Active projects", unit: "" },
  branches_total: { title: "Branches per project", unit: "" },
  compute_profiles: { title: "Compute sizes", unit: "" },
  storage_gb: { title: "Storage", unit: "GB" },
  agent_calls_per_day: { title: "Agent calls per day", used: "Agent calls today", unit: "" },
  backup_retention: { title: "Backups kept", unit: "" },
};

function capital(text) {
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

// An entitlement's title: "Storage", "Agent calls today".
export function entitlementTitle(entitlement) {
  const name = entitlement && typeof entitlement.name === "string" ? entitlement.name : "";
  if (Object.hasOwn(ENTITLEMENT_WORDS, name)) {
    return ENTITLEMENT_WORDS[name].title;
  }
  const unit = entitlement && typeof entitlement.unit === "string" ? entitlement.unit : "";
  return unit && unit !== "text" ? capital(unit) : "A limit of your plan";
}

function unitOf(entitlement) {
  const name = entitlement && entitlement.name;
  return Object.hasOwn(ENTITLEMENT_WORDS, name) ? ENTITLEMENT_WORDS[name].unit : "";
}

// An entitlement's value as words: "5 GB", "10,000", "small, standard, large",
// or its sentence; "not set" when the plan holds no number for it.
export function entitlementValue(entitlement) {
  const held = entitlement ? entitlement.value : null;
  if (typeof held === "number" && Number.isFinite(held)) {
    const unit = unitOf(entitlement);
    return `${held.toLocaleString("en-US")}${unit ? ` ${unit}` : ""}`;
  }
  if (Array.isArray(held)) {
    return held.join(", ");
  }
  return typeof held === "string" && held ? held : "not set";
}

// What is used of a read-not-enforced entitlement, from the usage figure the
// server reads it against: "Storage: 4.1 of 5 GB". Bytes are said in GB (10^9);
// a figure not read in the period is said, never read as none.
export function entitlementUse(entitlement, figures) {
  const name = entitlement && entitlement.name;
  const words = Object.hasOwn(ENTITLEMENT_WORDS, name) ? ENTITLEMENT_WORDS[name] : null;
  const title = words && words.used ? words.used : entitlementTitle(entitlement);
  const figure = figures && entitlement && typeof entitlement.against === "string" ? figures[entitlement.against] : null;
  const latest = figure && typeof figure.latest === "number" && Number.isFinite(figure.latest) ? figure.latest : null;
  const limit = entitlementValue(entitlement);
  if (latest === null) {
    return `${title}: not read in this period (the limit is ${limit})`;
  }
  const used = unitOf(entitlement) === "GB" ? (latest / 1e9).toFixed(1) : latest.toLocaleString("en-US");
  return `${title}: ${used} of ${limit}`;
}

// A server's sentence with every entitlement key it names replaced by that
// entitlement's title (the `limit_approaching` notice names its key, D3078).
// Keys from the served plan; a word that is no key is left as it is.
export function plainNotice(text, entitlements) {
  let said = typeof text === "string" ? text : "";
  for (const entitlement of Array.isArray(entitlements) ? entitlements : []) {
    const name = entitlement && typeof entitlement.name === "string" ? entitlement.name : "";
    if (/^[a-z][a-z0-9_]*$/.test(name)) {
      said = said.replace(new RegExp(`\\b${name}\\b`, "g"), entitlementTitle(entitlement));
    }
  }
  return said;
}

// The served entitlement a notice names by its key, or null.
export function noticeEntitlement(text, entitlements) {
  const said = typeof text === "string" ? text : "";
  return (Array.isArray(entitlements) ? entitlements : []).find((entitlement) =>
    entitlement && typeof entitlement.name === "string" && /^[a-z][a-z0-9_]*$/.test(entitlement.name)
      && new RegExp(`\\b${entitlement.name}\\b`).test(said)) || null;
}

// -- a destructive action's confirmation (D3088) ---------------------------------

// Whether what a person typed is the name of the thing a destructive action
// removes, exactly: the same characters, case and length -- nothing trimmed,
// nothing folded. An empty name confirms nothing. The dialog's button stays
// disabled until this is true (ADR 0295 decision 6, the brief's screen 9).
export function nameConfirmed(typed, name) {
  return typeof typed === "string" && typeof name === "string" && name.length > 0 && typed === name;
}

// -- usage in words (D3090) -------------------------------------------------------

// The usage document's gauges (`app.control_usage_document`'s `figures`, ADR
// 0275), in the order drawn, each with what a person calls it and how its
// number is said. A figure's key is never drawn.
export const USAGE_FIGURES = [
  { figure: "database_bytes", title: "Database size", kind: "bytes" },
  { figure: "repository_bytes", title: "Backup storage", kind: "bytes" },
  { figure: "branch_count", title: "Branches", kind: "count" },
  { figure: "branch_bytes", title: "Branch storage", kind: "bytes" },
  { figure: "customer_connections", title: "Connections", kind: "count" },
];

const BYTE_UNITS = ["KB", "MB", "GB", "TB", "PB"];

// A size in bytes as words: "512 bytes", "4.1 GB", "960 MB" -- decimal units
// (1 GB = 10^9 bytes, as the plans' `storage_gb` is read), one decimal below
// 10 and whole numbers above; a figure that would round to 1000 is said in the
// next unit. Null for anything that is not a size.
export function formatBytes(bytes) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) {
    return null;
  }
  if (bytes < 1000) {
    const whole = Math.round(bytes);
    return `${whole} byte${whole === 1 ? "" : "s"}`;
  }
  let scaled = bytes;
  for (let unit = 0; unit < BYTE_UNITS.length; unit += 1) {
    scaled /= 1000;
    const small = scaled < 9.95;
    const shown = small ? Math.round(scaled * 10) / 10 : Math.round(scaled);
    if (shown < 1000 || unit === BYTE_UNITS.length - 1) {
      return `${small ? shown.toFixed(1) : shown.toLocaleString("en-US")} ${BYTE_UNITS[unit]}`;
    }
  }
  return null;
}

// A count as words: "1", "18,342". Null for anything that is not a count.
export function formatCount(count) {
  return Number.isInteger(count) && count >= 0 ? count.toLocaleString("en-US") : null;
}

// One amount as words by its kind -- bytes, a count, or seconds -- or
// NOT_READ when the server read none (null or absent) or served something
// that is not one (ADR 0195: never a zero, never the raw value).
export function usageAmount(kind, amount) {
  if (amount === null || amount === undefined) {
    return NOT_READ;
  }
  const words = kind === "bytes" ? formatBytes(amount) : kind === "seconds" ? formatDuration(amount) : formatCount(amount);
  return words === null ? NOT_READ : words;
}

// The exact byte count behind a size, for a title ("4,100,000,000 bytes");
// null for any other kind, or an amount that is not a size.
export function usageDetail(kind, amount) {
  return kind === "bytes" && formatBytes(amount) !== null ? `${amount.toLocaleString("en-US")} bytes` : null;
}

// Each gauge of a usage document's `figures` as a row of words: its title,
// the latest reading and when it was read (only when it was), the highest in
// the period, each size's exact bytes, and how many samples could not read it.
export function usageRows(figures) {
  const all = figures && typeof figures === "object" ? figures : {};
  return USAGE_FIGURES.map(({ figure, title, kind }) => {
    const read = all[figure] && typeof all[figure] === "object" ? all[figure] : {};
    const latest = usageAmount(kind, read.latest);
    return {
      figure,
      title,
      latest,
      latest_detail: usageDetail(kind, read.latest),
      latest_at: latest === NOT_READ ? null : read.latest_at || null,
      max: usageAmount(kind, read.max),
      max_detail: usageDetail(kind, read.max),
      unread_samples: Number.isInteger(read.unread_samples) ? read.unread_samples : null,
    };
  });
}

// The usage document's other figures, as words: the requests answered, the
// agent calls and workflow runs summed over the period, and the time awake and
// asleep from the project's history (`app.control_usage_document`).
export function usageTotals(served) {
  const read = served && typeof served === "object" ? served : {};
  const requests = read.requests && typeof read.requests === "object" ? read.requests.increase : null;
  return [
    { figure: "requests", title: "Requests answered (below 400)", value: usageAmount("count", requests) },
    { figure: "agent_calls", title: "Agent calls", value: usageAmount("count", read.agent_calls) },
    { figure: "workflow_runs", title: "Workflow runs", value: usageAmount("count", read.workflow_runs) },
    { figure: "active_seconds", title: "Time awake", value: usageAmount("seconds", read.active_seconds) },
    { figure: "sleeping_seconds", title: "Time asleep", value: usageAmount("seconds", read.sleeping_seconds) },
  ];
}

// -- the notifications' count (D3001) ---------------------------------------------

export const RECENT_HOURS = 24;

// How many of the notifications read were written in the 24 hours before
// `now`, as a sentence: a count of what the API served, never an UNREAD count
// -- the server keeps no read state ("In-app only; no read state") and this
// console keeps nothing (ADR 0281). `asked` is the page's `limit`: when every
// notification read falls in the window there may be more, and the count says
// "at least". A time that cannot be read is counted apart, never in or out of
// the window (ADR 0195).
export function recentNotices(notifications, now, asked) {
  const list = Array.isArray(notifications) ? notifications : [];
  let recent = 0;
  let undated = 0;
  for (const notice of list) {
    const age = elapsedSeconds(notice ? notice.created_at : null, now);
    if (age === null) {
      undated += 1;
    } else if (age <= RECENT_HOURS * 3600) {
      recent += 1;
    }
  }
  const more = typeof asked === "number" && recent > 0 && recent === list.length && list.length >= asked;
  const head = recent === 0
    ? `None in the last ${RECENT_HOURS} hours.`
    : `${more ? "At least " : ""}${recent} in the last ${RECENT_HOURS} hours.`;
  return undated ? `${head} ${undated} more could not be dated.` : head;
}

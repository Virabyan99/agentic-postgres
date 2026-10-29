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
    ? (me.second_factor.enabled ? DONE : NOT_YET)
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

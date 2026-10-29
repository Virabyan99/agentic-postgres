// A long operation's progress, in words (ADR 0296): DOM-free, so Node can drive
// it (tests/contract/test_console_progress.py). It imports nothing and keeps
// nothing; every answer is computed from the operation the API served -- its
// `status`, `step`, `steps` ([{step, started_at}], when each step first began)
// and `expected` ({steps: [{step, label, typical_seconds}], typical_seconds:
// {low, high}, bound_seconds}, the server's `operation_steps`) -- and the time
// `now` (milliseconds, the browser's clock). An elapsed time is the browser's
// clock against the server's, so the page says "about". A value the operation
// does not carry is `null`, never 0 (ADR 0195).

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

// What each refusal means, and what to do next (ADR 0297 decision 3). Every
// word the console can meet is `{sentence, action, link}`: the sentence says
// what happened, in the customer's terms; the action what they can do now (a
// page to go to, or what to wait for); the link, when there is one, goes there
// -- a console route (`#/...`) or a page of the site (`/...`, on the site this
// console belongs to, derived from this page's host). The API's own word is
// shown under the sentence in small type, for whoever helps.
//
// The set is DERIVED, never typed (D2989): tests/contract/test_console_refusals.py
// reads every word the management API can answer from the server's modules --
// `errors.CONTROL_STATUS`, the error documents the control modules use
// (through an `errors.*()` helper too), `OPERATION_ERROR_CODES` -- with the
// console's own words from `api.js`, and the relay's close codes (ADR 0286) with
// 1000, 1006 and 1011; it fails on a word without an entry here and on an entry
// for no word.

import { Refusal } from "/console/api.js";
import { h, siteLink } from "/console/ui.js";

export const REFUSALS = {
  authentication_failed: {
    sentence: "You are not signed in, or the username or the password is not right.",
    action: "Sign in again", link: "#/sign-in",
  },
  authorization_failed: {
    sentence: "Your role in this organisation does not allow this; nothing was changed.",
    action: "Ask an owner of the organisation to change your role", link: null,
  },
  malformed_request: {
    sentence: "The page sent something the server could not read; nothing was changed.",
    action: "Reload the page and try again. If it happens again, ask for help", link: "#/help",
  },
  invalid_request: {
    sentence: "The server could not act on what was asked; nothing was changed.",
    action: "Check what you entered, then try again", link: null,
  },
  not_found: {
    sentence: "Nothing by that name is here, or it is not yours to see.",
    action: "Go to your projects", link: "#/",
  },
  conflict: {
    sentence: "Another operation is still running on this, so nothing new was recorded.",
    action: "Wait for it to finish, then try again", link: null,
  },
  last_owner: {
    sentence: "This is the organisation's last owner, so the role cannot be changed and the member cannot be removed.",
    action: "Make another member an owner first", link: null,
  },
  plan_limit_reached: {
    sentence: "Your organisation already holds every project its plan allows (one being created counts); nothing was recorded.",
    action: "See the plans", link: "/pricing/",
  },
  branch_limit_reached: {
    sentence: "This project already has every branch its plan allows, or one is being made; nothing was recorded.",
    action: "Delete a branch, or see the plans", link: "/pricing/",
  },
  capacity_exhausted: {
    sentence: "No server slot is ready for a new project right now, so nothing was created.",
    action: "Try again later, or ask for help", link: "#/help",
  },
  not_available: {
    sentence: "That is not offered yet; nothing was changed.",
    action: "Read what is offered", link: "/docs/",
  },
  human_session_required: {
    sentence: "Only a person signed in to the console may do this, not a management key.",
    action: "Sign in to the console as yourself", link: "#/sign-in",
  },
  factor_enabled: {
    sentence: "This account already has a second factor; nothing was changed.",
    action: "Go to your projects", link: "#/",
  },
  second_factor_required: {
    sentence: "This account signs in with a second factor.",
    action: "Enter the six-digit code your authenticator app shows now", link: null,
  },
  second_factor_invalid: {
    sentence: "That code is wrong, or it was already used.",
    action: "Wait for the next code in your app, then enter it", link: null,
  },
  invitation_invalid: {
    sentence: "This invitation link was already used, has expired, was revoked, or is not known.",
    action: "Ask whoever invited you for a new link", link: null,
  },
  username_taken: {
    sentence: "That username is taken.",
    action: "Choose another; the invitation still works", link: null,
  },
  could_not_determine: {
    sentence: "The server could not tell how this ended, and it does not guess.",
    action: "Look at the project's state; if it is unclear, ask for help", link: "#/help",
  },
  interrupted: {
    sentence: "The operation was interrupted before it finished, and was stopped.",
    action: "Start it again. If it happens again, ask for help", link: "#/help",
  },
  operation_failed: {
    sentence: "The operation failed on the server before it finished.",
    action: "Try again. If it fails again, ask for help and send the support bundle", link: "#/help",
  },
  console_unconfigured: {
    sentence: "The console is not set up on this server yet.",
    action: "Ask for help", link: "#/help",
  },
  unexpected_answer: {
    sentence: "The server's answer could not be read by this page.",
    action: "Reload the page. If it happens again, ask for help", link: "#/help",
  },
};

// The SQL editor's socket, closed by the relay (ADR 0286) or by the browser.
export const CLOSES = {
  1000: {
    sentence: "The session closed normally.",
    action: null, link: null,
  },
  1006: {
    sentence: "The connection to the editor's relay was lost, or could not be opened.",
    action: "Check your network, then connect again", link: null,
  },
  1011: {
    sentence: "The relay failed while it carried the session.",
    action: "Connect again. If it happens again, ask for help", link: "#/help",
  },
  4400: {
    sentence: "The relay refused a message it does not carry, and closed the session.",
    action: "Connect again", link: null,
  },
  4408: {
    sentence: "The session ended: it ran for 30 minutes, or sat idle for 5.",
    action: "Connect again", link: null,
  },
  4413: {
    sentence: "The session carried more than the relay allows, and was closed.",
    action: "Ask for fewer rows at a time, then connect again", link: null,
  },
  4429: {
    sentence: "Too many editor sessions are open on this server.",
    action: "Try again in a minute", link: null,
  },
  4502: {
    sentence: "The relay could not reach your database.",
    action: "If the project is asleep, wake it from its Settings page, then connect again", link: null,
  },
};

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function planName(plan) {
  return typeof plan === "string" && plan ? plan.charAt(0).toUpperCase() + plan.slice(1) : null;
}

// A word's entry, its sentence made exact by what the refusal's own body
// carries: `plan_limit_reached` and `branch_limit_reached` name the plan and
// its number when the server sent them (ADR 0297 decision 4, D2996).
export function wording(code, body) {
  const known = Object.hasOwn(REFUSALS, code) ? REFUSALS[code] : null;
  if (!known) {
    return { sentence: "The server refused this.", action: "Ask for help, and give them the word below", link: "#/help" };
  }
  const plan = planName(body && body.plan);
  const limit = body && typeof body.limit === "number" ? body.limit : null;
  if (code === "plan_limit_reached" && plan && limit !== null) {
    return { ...known, sentence: `Your ${plan} plan holds ${plural(limit, "project")}, and this organisation already has that many (one being created counts); nothing was recorded.` };
  }
  if (code === "branch_limit_reached" && plan && limit !== null) {
    return { ...known, sentence: `Your ${plan} plan allows ${limit} ${limit === 1 ? "branch" : "branches"} per project, and this project has that many or one is being made; nothing was recorded.` };
  }
  return known;
}

// The sentence a refusal's word stands for.
export function sentence(code) {
  return wording(code, null).sentence;
}

// An action as a link, or as plain words when there is nowhere to go.
function next(word) {
  if (!word.action) {
    return null;
  }
  if (!word.link) {
    return h("span", { className: "action" }, word.action + ".");
  }
  return h("a", { href: word.link.startsWith("#") ? word.link : siteLink(word.link) }, word.action);
}

// The organisation's Plan page, beside a plan limit's link to the site's plans
// (ADR 0297 decision 6), when the view knows the organisation.
function planPage(code, organization) {
  return organization && (code === "plan_limit_reached" || code === "branch_limit_reached")
    ? [" · ", h("a", { href: `#/org/${organization}/plan` }, "Your plan")]
    : null;
}

// One word as a paragraph: what happened, what to do, and the word itself in
// small type (the brief's screen 5).
export function said(code, body, options) {
  const { organization = null, className = "refusal" } = options || {};
  const word = wording(code, body);
  const named = body && body.row ? [" (Ledger row ", h("code", {}, body.row), ")"] : [];
  const action = next(word);
  return h("p", { className, role: "alert" },
    word.sentence, ...named, action ? [" ", action] : null, planPage(code, organization),
    h("code", { className: "word" }, code));
}

// A refusal as a paragraph; a failure to reach the server at all is said so.
export function refusal(error, options) {
  if (error instanceof Refusal) {
    return said(error.code, error.body, options);
  }
  return h("p", { className: "refusal", role: "alert" }, "The server could not be reached. Check your network, then try again.");
}

// How an editor session ended, from its close code; null for a code with no entry.
export function closeWords(code) {
  return Object.hasOwn(CLOSES, code) ? CLOSES[code] : null;
}

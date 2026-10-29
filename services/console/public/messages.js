// What each refusal means, and what to do next (ADR 0297). Every word the
// console meets is `{sentence, action, link}`: the sentence says what is true,
// in the words the documentation uses; the action says what would change it;
// the link, when there is one, goes there -- a console route (`#/...`) or a
// page of the site (`/...`, on the site this console belongs to). Run 5
// derives the whole set from the server's modules; these are the words the
// console has answered since Session 46.

import { Refusal } from "/console/api.js";
import { h, siteLink } from "/console/ui.js";

export const REFUSALS = {
  authentication_failed: {
    sentence: "The username or the password is not right, or the session has ended.",
    action: "Sign in again", link: "#/sign-in",
  },
  authorization_failed: {
    sentence: "Your role in this organisation does not allow this.",
    action: "Ask an owner of the organisation to change your role", link: null,
  },
  second_factor_required: {
    sentence: "Enter the six-digit code from your authenticator app.",
    action: null, link: null,
  },
  second_factor_invalid: {
    sentence: "That code is wrong, or it was already used. Wait for the next one.",
    action: null, link: null,
  },
  invitation_invalid: {
    sentence: "This invitation is used, expired, revoked or unknown. Ask for a new one.",
    action: "Ask whoever invited you for a new link", link: null,
  },
  username_taken: {
    sentence: "That username is taken. Choose another; the invitation is still good.",
    action: null, link: null,
  },
  factor_enabled: {
    sentence: "A second factor is already enabled for this account.",
    action: null, link: null,
  },
  human_session_required: {
    sentence: "Only a signed-in person may do this, not a management key.",
    action: null, link: null,
  },
  not_found: {
    sentence: "Nothing by that name here, or it is not yours to see.",
    action: "Go to your projects", link: "#/",
  },
  plan_limit_reached: {
    sentence: "The organisation already holds its plan's projects; nothing was recorded.",
    action: "See the plans", link: "/pricing/",
  },
  capacity_exhausted: {
    sentence: "No room on this server; nothing was recorded.",
    action: "Try again later, or ask for help", link: "#/help",
  },
  conflict: {
    sentence: "Another operation is in flight; nothing was recorded.",
    action: "Wait for it to finish, then try again", link: null,
  },
  branch_limit_reached: {
    sentence: "The project already has its plan's branches, or one is being made; nothing was recorded.",
    action: "See the plans", link: "/pricing/",
  },
  not_available: {
    sentence: "That is not offered yet.",
    action: null, link: null,
  },
  invalid_request: {
    sentence: "The request named something this cannot act on.",
    action: null, link: null,
  },
  console_unconfigured: {
    sentence: "The console is not configured on this server.",
    action: "Ask for help", link: "#/help",
  },
};

// A word's action as a link, or as plain words when there is nowhere to go.
function next(word) {
  if (!word.action) {
    return null;
  }
  if (!word.link) {
    return h("span", { className: "action" }, word.action + ".");
  }
  return h("a", { href: word.link.startsWith("#") ? word.link : siteLink(word.link) }, word.action);
}

// The sentence a refusal's word stands for.
export function sentence(code) {
  return Object.hasOwn(REFUSALS, code) ? REFUSALS[code].sentence : "The server refused this.";
}

// A refusal as a paragraph: what is true, what to do, and the API's word in
// small type for whoever helps.
export function refusal(error) {
  if (error instanceof Refusal) {
    const word = Object.hasOwn(REFUSALS, error.code) ? REFUSALS[error.code] : null;
    const named = error.body && error.body.row ? [" (Ledger row ", h("code", {}, error.body.row), ")"] : [];
    const action = word ? next(word) : null;
    return h("p", { className: "refusal", role: "alert" },
      sentence(error.code), ...named, action ? [" ", action] : null, " ", h("code", { className: "word" }, error.code));
  }
  return h("p", { className: "refusal", role: "alert" }, "The server could not be reached.");
}

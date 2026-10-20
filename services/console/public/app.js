// The console's views (ADR 0280). Two pages share this file: `/accept`, where
// an invitation link becomes an account (ADR 0282), and `/console/`, whose
// views are fragment routes (`#/`, `#/sign-in`).
//
// Rules this file keeps, each held by tests/contract/test_console_pages.py:
// every value from the server is set with `textContent` or a DOM property,
// never parsed as markup; nothing is written to localStorage, sessionStorage,
// indexedDB or document.cookie (the session is two HttpOnly cookies this code
// cannot read); a secret -- a password, the factor's seed -- lives in a local
// variable for the length of one view and is never put in a URL.

import { call, Refusal } from "/console/api.js";

// What each refusal means, in the words the documentation uses.
const REFUSALS = {
  authentication_failed: "The username or the password is not right, or the session has ended.",
  second_factor_required: "Enter the six-digit code from your authenticator app.",
  second_factor_invalid: "That code is wrong, or it was already used. Wait for the next one.",
  invitation_invalid: "This invitation is used, expired, revoked or unknown. Ask for a new one.",
  username_taken: "That username is taken. Choose another; the invitation is still good.",
  factor_enabled: "A second factor is already enabled for this account.",
  human_session_required: "Only a signed-in person may do this, not a management key.",
  plan_limit_reached: "The organisation already holds its plan's projects; nothing was recorded.",
  capacity_exhausted: "No room on this server; nothing was recorded.",
  conflict: "Another operation is in flight; nothing was recorded.",
  not_available: "That is not offered yet.",
  console_unconfigured: "The console is not configured on this server.",
};

const main = document.getElementById("main");

// One element, its properties and its children -- strings become text nodes.
function h(tag, properties, ...children) {
  const element = document.createElement(tag);
  for (const [name, value] of Object.entries(properties || {})) {
    if (name.startsWith("on")) {
      element.addEventListener(name.slice(2), value);
    } else {
      element[name] = value;
    }
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) {
      element.append(typeof child === "string" ? document.createTextNode(child) : child);
    }
  }
  return element;
}

function show(...nodes) {
  main.replaceChildren(...nodes);
}

function refusal(error) {
  if (error instanceof Refusal) {
    const sentence = REFUSALS[error.code] || "The server refused this.";
    return h("p", { className: "refusal", role: "alert" }, h("code", {}, error.code), " ", sentence);
  }
  return h("p", { className: "refusal", role: "alert" }, "The server could not be reached.");
}

function field(label, properties) {
  const input = h("input", properties);
  return [h("label", {}, label, input), input];
}

// -- the second factor, shared by onboarding and sign-in --------------------

// Begins enrolment, shows the QR and the base32 text under it, confirms with a
// code. Resolves once confirmed: confirming ends every session (the server's
// rule), so the caller signs in again with the NEXT code.
function enrolFactor() {
  return new Promise((resolve) => {
    const status = h("div", {});
    show(h("h1", {}, "Set up your second factor"), status);
    call("POST", "/me/totp").then((enrolment) => {
      const [codeLabel, code] = field("Code from your app", {
        inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
      });
      const message = h("div", {});
      const confirm = h("button", {
        type: "button",
        onclick: async () => {
          message.replaceChildren();
          try {
            await call("POST", "/me/totp/confirm", { totp_code: code.value.trim() });
          } catch (error) {
            message.replaceChildren(refusal(error));
            return;
          }
          enrolment = null;
          resolve();
        },
      }, "Confirm");
      status.replaceChildren(
        h("p", {}, "Scan this with your authenticator app, then enter the code it shows."),
        h("img", { src: enrolment.otpauth_qr, alt: "QR code for your authenticator app", className: "qr" }),
        h("p", {}, "Or type this key into the app: ", h("code", { className: "secret" }, enrolment.secret)),
        codeLabel, confirm, message,
      );
    }).catch((error) => status.replaceChildren(refusal(error)));
  });
}

async function signIn(username, password, totpCode) {
  const body = { username, password };
  if (totpCode) {
    body.totp_code = totpCode;
  }
  return call("POST", "/sessions", body);
}

// -- /accept: an invitation link becomes an account ---------------------------

async function acceptPage() {
  // The token leaves the address bar BEFORE the first request (ADR 0282): a
  // fragment is never sent, and now it is not in the history either.
  const token = location.hash.length > 1 ? location.hash.slice(1) : "";
  history.replaceState(null, "", "/accept");
  if (!/^[A-Za-z0-9_-]+$/.test(token)) {
    show(h("h1", {}, "Invitation"), h("p", {}, "This link holds no invitation. Open the link you were sent."));
    return;
  }
  let me = null;
  try {
    me = await call("GET", "/me");
  } catch (error) {
    me = null;
  }
  if (me) {
    joinAsSignedIn(token, me);
  } else {
    createAccount(token);
  }
}

function joinAsSignedIn(token, me) {
  const message = h("div", {});
  show(
    h("h1", {}, "Join with your account"),
    h("p", {}, "You are signed in as ", h("strong", {}, me.username), "."),
    h("button", {
      type: "button",
      onclick: async () => {
        try {
          await call("POST", "/invitations/accept", { invitation_token: token });
          location.assign("/console/");
        } catch (error) {
          message.replaceChildren(refusal(error));
        }
      },
    }, "Join"),
    message,
  );
}

function createAccount(token) {
  const [userLabel, username] = field("Username", { autocomplete: "username", required: true });
  const [displayLabel, display] = field("Display name", { autocomplete: "name" });
  const [passLabel, password] = field("Password", { type: "password", autocomplete: "new-password" });
  const [againLabel, again] = field("Password again", { type: "password", autocomplete: "new-password" });
  const message = h("div", {});
  const create = h("button", {
    type: "button",
    onclick: async () => {
      message.replaceChildren();
      if (password.value !== again.value) {
        message.replaceChildren(h("p", { className: "refusal" }, "The two passwords differ."));
        return;
      }
      const name = username.value.trim();
      const secret = password.value;
      try {
        await call("POST", "/invitations/accept", {
          invitation_token: token, username: name,
          display_name: display.value.trim() || name, password: secret,
        });
        await signIn(name, secret);
        const self = await call("GET", "/me");
        if (self.second_factor.required && !self.second_factor.enabled) {
          await enrolFactor();
          await signInWithNextCode(name, secret);
        }
      } catch (error) {
        message.replaceChildren(refusal(error));
        return;
      } finally {
        password.value = "";
        again.value = "";
      }
      location.assign("/console/");
    },
  }, "Create your account");
  show(
    h("h1", {}, "Create your account"),
    h("p", {}, "You were invited. Choose a username and a password."),
    userLabel, displayLabel, passLabel, againLabel, create, message,
  );
}

// After a factor is confirmed every session has ended; the next code signs in.
function signInWithNextCode(username, password) {
  return new Promise((resolve) => {
    const [codeLabel, code] = field("The next code from your app", {
      inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
    });
    const message = h("div", {});
    show(
      h("h1", {}, "Sign in"),
      h("p", {}, "Your second factor is on. Wait for the next code in your app and enter it."),
      codeLabel,
      h("button", {
        type: "button",
        onclick: async () => {
          try {
            await signIn(username, password, code.value.trim());
          } catch (error) {
            message.replaceChildren(refusal(error));
            return;
          }
          resolve();
        },
      }, "Sign in"),
      message,
    );
  });
}

// -- /console/: sign-in and the overview --------------------------------------

function signInView() {
  const [userLabel, username] = field("Username", { autocomplete: "username" });
  const [passLabel, password] = field("Password", { type: "password", autocomplete: "current-password" });
  const [codeLabel, code] = field("Code from your app", {
    inputMode: "numeric", autocomplete: "one-time-code", maxLength: 6,
  });
  codeLabel.hidden = true;
  const message = h("div", {});
  show(
    h("h1", {}, "Sign in"),
    userLabel, passLabel, codeLabel,
    h("button", {
      type: "button",
      onclick: async () => {
        message.replaceChildren();
        try {
          await signIn(username.value.trim(), password.value, code.value.trim() || undefined);
        } catch (error) {
          if (error instanceof Refusal && error.code === "second_factor_required") {
            codeLabel.hidden = false;
          }
          message.replaceChildren(refusal(error));
          return;
        }
        password.value = "";
        location.hash = "#/";
        route();
      },
    }, "Sign in"),
    message,
  );
}

async function signOut() {
  try {
    await call("DELETE", "/sessions/current");
  } finally {
    location.hash = "#/sign-in";
    route();
  }
}

async function overview() {
  let me;
  try {
    me = await call("GET", "/me");
  } catch (error) {
    signInView();
    return;
  }
  if (me.second_factor.required && !me.second_factor.enabled) {
    show(h("p", {}, "Set up your second factor before anything else."));
    await enrolFactor();
    location.hash = "#/sign-in";
    route();
    return;
  }
  const organizations = (await call("GET", "/organizations")).organizations;
  const sections = [];
  for (const organization of organizations) {
    const query = "?organization=" + encodeURIComponent(organization.id);
    const projects = (await call("GET", "/projects" + query)).projects;
    sections.push(h("section", {},
      h("h2", {}, organization.name || organization.id, " ", h("small", {}, organization.role)),
      projects.length === 0
        ? h("p", {}, "No project yet.")
        : h("ul", {}, projects.map((project) => h("li", {},
          h("code", {}, project.key), " ", project.state || ""))),
    ));
  }
  show(
    h("header", { className: "bar" },
      h("span", {}, "Signed in as ", h("strong", {}, me.username)),
      h("button", { type: "button", onclick: signOut }, "Sign out")),
    h("h1", {}, "Overview"),
    organizations.length === 0 ? h("p", {}, "You belong to no organisation yet.") : sections,
  );
}

function route() {
  if (location.hash === "#/sign-in") {
    signInView();
  } else {
    overview();
  }
}

if (location.pathname === "/accept") {
  acceptPage();
} else {
  window.addEventListener("hashchange", route);
  route();
}

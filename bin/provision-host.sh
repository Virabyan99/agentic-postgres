#!/usr/bin/env bash
#
# Bring a fresh Ubuntu host to the Session 2 baseline.
#
# This is the script that can lock you out of your own server, so its shape is
# dictated by §3 of the implementation plan rather than by convenience:
#
#   * --check is the default and changes nothing. --apply is explicit.
#   * SSH hardening refuses to run unless a rollback timer is already armed.
#     The timer is not armed by this script as a side effect of --apply,
#     because a rollback you did not deliberately arm is one you will not
#     remember to disarm.
#   * The firewall is never enabled before a rule permitting the configured SSH
#     port exists. Enabling UFW with default-deny and no SSH allow is the
#     classic lockout, and it is one ordering mistake away at all times.
#   * Nothing is disarmed automatically. --confirm-ssh-ok is a separate
#     invocation, because auto-cancelling on "the script finished" cancels on
#     exactly the case where the script was wrong.
#
# Exit codes:
#   0  success, or --check found everything in policy
#   2  invalid operator input
#   3  missing prerequisite, unsupported host, or not root
#   6  a hardening or firewall step failed, or --check found a violation

set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT_DIR

readonly ETC="/etc/agentic-postgres"
readonly LIBEXEC="/usr/local/libexec/agentic-postgres"
readonly SYSTEMD_DIR="/etc/systemd/system"
readonly BACKUP_ROOT="/var/backups/agentic-postgres"
readonly SSH_SNIPPET="/etc/ssh/sshd_config.d/00-agentic-postgres-ssh.conf"
readonly ROLLBACK_UNIT="apg-ssh-rollback"
readonly UFW_ROLLBACK_UNIT="apg-ufw-rollback"
# The one sudo rule this system installs (ADR 0043). It names the database
# access trampoline by a path that never changes, so it is written once here and
# never rewritten per release -- which is the practical reason that split is
# cheap as well as correct. The rule permits invoking one program; what that
# program hands over is decided by the release it resolves to and by the policy
# file, neither of which sudo knows anything about.
readonly SUDOERS_FILE="/etc/sudoers.d/agentic-postgres-database-access"

# The directives whose *resolved* value decides whether an operator can still
# get in, and whether the hardening did anything. One list, used both by --check
# to report and by --apply to refuse: a baseline that reports on one set while
# the safety gate enforces another is two policies wearing one name.
#
# Resolved, not configured. OpenSSH takes the first obtained value across a
# lexicographic include order and Match blocks override regardless of order, so
# what our file says and what sshd decided are different questions.
readonly SSHD_REQUIRED_POLICY=(
  "pubkeyauthentication yes"
  "passwordauthentication no"
  "permitrootlogin no"
  "kbdinteractiveauthentication no"
  "permitemptypasswords no"
)

MODE="check"
HOST_MANIFEST=""
CONFIRM_SSH_OK=0
CONFIRM_FIREWALL_OK=0

usage() {
  cat <<'USAGE'
Usage: sudo bin/provision-host.sh --host FILE [--check | --apply]
       sudo bin/provision-host.sh --host FILE --confirm-ssh-ok
       sudo bin/provision-host.sh --host FILE --confirm-firewall-ok

  --check   Report every deviation from the Session 2 baseline and change
            nothing. This is the default.
  --apply   Bring the host to the baseline.
  --confirm-ssh-ok
            Disarm the SSH rollback timer. Run this only after opening a NEW
            SSH session with a key and confirming it works. It is separate on
            purpose: a script that cancelled its own rollback would cancel it
            in exactly the case where the script was wrong.
  --confirm-firewall-ok
            Disarm the firewall rollback timer. Same rule: only after a NEW
            session has connected through the enabled firewall.

  --host FILE  The host manifest.

The two locking-out steps each refuse to run until their own rollback timer is
armed, and only one may be armed at a time. A fresh host therefore takes three
--apply passes, which is the cost of never having two unverified windows open
at once:

  1. --apply            installs launchers, units and Docker; skips both.
  2. arm apg-ssh-rollback, --apply, verify a NEW session, --confirm-ssh-ok.
  3. arm apg-ufw-rollback, --apply, verify a NEW session, --confirm-firewall-ok.

Each --apply prints the exact arm command for the step it skipped, including
the backup directory it just created. If a new session fails after either step,
do nothing for ten minutes and let the timer undo it.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'provision-host: %s\n' "$*" >&2
  exit "$code"
}

# Interpreter resolution, in this order and for these reasons:
#
#   1. the repository's own venv, because sudo resets PATH to secure_path and a
#      venv the operator activated is therefore invisible to this script;
#   2. python3, because Ubuntu ships no bare `python` and has not for years;
#   3. python, for a machine where the venv is already on PATH.
#
# Assuming a bare `python` is a standing trap this repository documents, and
# five Session 2 scripts walked into it. It fails only on a host, only under
# sudo, and reports `python: command not found` from inside a heredoc.
python_bin() {
  if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    printf '%s' "${ROOT_DIR}/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    die 3 "no Python interpreter found (looked for .venv/bin/python, python3, python)."
  fi
}

note() { printf '  %s\n' "$*"; }
ok() { printf '  ok      %s\n' "$*"; }
bad() { printf '  DEVIATE %s\n' "$*"; }

parse_arguments() {
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --help|-h) usage; exit 0 ;;
      --check) MODE="check"; shift ;;
      --apply) MODE="apply"; shift ;;
      --confirm-ssh-ok) CONFIRM_SSH_OK=1; shift ;;
      --confirm-firewall-ok) CONFIRM_FIREWALL_OK=1; shift ;;
      --host)
        [ "$#" -ge 2 ] || die 2 "--host requires a value."
        HOST_MANIFEST="$2"
        shift 2
        ;;
      *) usage >&2; die 2 "unknown argument: $1" ;;
    esac
  done

  [ -n "${HOST_MANIFEST}" ] || die 2 "--host is required."
  [ -f "${HOST_MANIFEST}" ] || die 2 "host manifest not found: ${HOST_MANIFEST}"

  # Resolved here, while the caller's working directory is still the one they
  # typed the path against. main() cd's to ${ROOT_DIR} before anything reads
  # this file, so a relative --host would be re-resolved against the checkout:
  # `--host host.yaml` from /tmp validates /tmp/host.yaml and then reads the
  # checkout's. Being handed a manifest for a different host and provisioning
  # from it is the quietest possible version of this going wrong.
  HOST_MANIFEST="$(readlink -f -- "${HOST_MANIFEST}")" \
    || die 2 "could not resolve an absolute path for the host manifest."
  readonly HOST_MANIFEST

  # Validated once, here, so an invalid manifest is one message and exit 2 --
  # the documented code for invalid operator input. Without this the first
  # host_field call raises a Python traceback out of a heredoc and the script
  # exits 1, which reads like a bug in the tool rather than a bad input file.
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${HOST_MANIFEST}" <<'PYTHON' \
    || die 2 "the host manifest is not valid; nothing was read from it."
import sys
from pathlib import Path

from agentic_postgres.config import ManifestError
from agentic_postgres.host_config import load_host_manifest

try:
    load_host_manifest(Path(sys.argv[1]))
except (ManifestError, OSError) as error:
    sys.exit(f"provision-host: {error}")
PYTHON
}

host_field() {
  PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${HOST_MANIFEST}" "$1" <<'PYTHON'
import sys
from pathlib import Path

from agentic_postgres.host_config import load_host_manifest

# Resolved from the whole document, not from the host block. `host`, `ssh`,
# `edge` and `infisical` are siblings, so a path is written in full:
# "ssh.port", "host.public_interface". Starting inside `host` made every
# caller's path wrong and produced a bare KeyError with no field name in it.
document = load_host_manifest(Path(sys.argv[1]))
value = document
for part in sys.argv[2].split("."):
    if not isinstance(value, dict) or part not in value:
        sys.exit(f"host manifest has no field {sys.argv[2]!r} (stopped at {part!r})")
    value = value[part]
print(value)
PYTHON
}

# ---------------------------------------------------------------------------
# Checks. Every one of these runs in --check and again after --apply.
# ---------------------------------------------------------------------------

check_baseline() {
  local violations=0 ssh_port
  ssh_port="$(host_field ssh.port)"

  printf '\n== host ==\n'
  if [ "$(uname -m)" = "x86_64" ]; then
    ok "architecture x86_64"
  else
    bad "architecture $(uname -m); every locked digest is linux/amd64"
    violations=$((violations + 1))
  fi

  # Parsed, not sourced. /etc/os-release is a shell fragment by convention and
  # sourcing it executes it; reading one field with grep does not, and the
  # difference is that this script runs as root.
  local release
  release="$(grep -m1 '^VERSION_ID=' /etc/os-release 2>/dev/null | cut -d= -f2- | tr -d '"')"
  case "${release}" in
    24.04|26.04) ok "Ubuntu ${release}" ;;
    *)
      bad "Ubuntu ${release:-unknown} is not a supported release"
      violations=$((violations + 1))
      ;;
  esac

  if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
    ok "clock is synchronised"
  else
    # A skewed clock breaks ACME validation in a way whose error message is
    # about certificates rather than about time.
    bad "clock is not NTP-synchronised; ACME will fail confusingly"
    violations=$((violations + 1))
  fi

  printf '\n== ssh ==\n'
  if [ -f "${SSH_SNIPPET}" ]; then
    ok "snippet installed at ${SSH_SNIPPET}"
  else
    bad "snippet is not installed"
    violations=$((violations + 1))
  fi

  if command -v sshd >/dev/null 2>&1; then
    local resolved
    resolved="$(sshd -T 2>/dev/null || true)"
    for pair in "${SSHD_REQUIRED_POLICY[@]}"; do
      if printf '%s\n' "${resolved}" | grep -qi "^${pair}$"; then
        ok "sshd resolved ${pair}"
      else
        # Resolved, not configured. OpenSSH takes the first obtained value
        # across a lexicographic include order, so what our file says and what
        # sshd decided are different questions.
        bad "sshd did not resolve ${pair}; an earlier include may be winning"
        violations=$((violations + 1))
      fi
    done
  fi

  printf '\n== installed release ==\n'
  # Checked because both launchers refuse without it, and a unit that cannot
  # start is invisible until the reboot that needed it.
  if [ -f "${ETC}/edge-state.json" ]; then
    local recorded release_dir
    recorded="$(sed -n 's/.*"installed_release_commit": "\([0-9a-f]\{40\}\)".*/\1/p' \
      "${ETC}/edge-state.json")"
    release_dir="/opt/agentic-postgres/releases/${recorded}"
    if [ -n "${recorded}" ] && [ -d "${release_dir}" ]; then
      ok "release ${recorded:0:12} installed and recorded"
    else
      bad "edge-state.json names no installed release the launchers can resolve"
      violations=$((violations + 1))
    fi
  else
    bad "${ETC}/edge-state.json is absent; the launchers cannot resolve a release"
    violations=$((violations + 1))
  fi

  printf '\n== launchers and units ==\n'
  # Checked because the units name these paths and nothing else. A unit whose
  # Exec* target is absent fails at boot with a message about the unit rather
  # than about the missing file.
  local launcher
  for launcher in edge project firewall ssh-rollback database-access; do
    if [ -x "${LIBEXEC}/${launcher}" ]; then
      ok "launcher ${launcher}"
    else
      bad "launcher ${launcher} is not installed at ${LIBEXEC}/${launcher}"
      violations=$((violations + 1))
    fi
  done

  # The sudo rule, checked for the two things that make it either useless or
  # dangerous: a mode sudo refuses to read, and a rule naming an account that is
  # not the operator this host is configured for.
  if [ -f "${SUDOERS_FILE}" ]; then
    local sudoers_mode
    sudoers_mode="$(stat -c '%a' "${SUDOERS_FILE}")"
    if [ "${sudoers_mode}" = "440" ]; then
      ok "sudoers rule ${SUDOERS_FILE}"
    else
      bad "${SUDOERS_FILE} is mode ${sudoers_mode}; sudo ignores a file that is not 0440 or tighter"
      violations=$((violations + 1))
    fi
    if grep -q "^$(host_field ssh.operator_user) ALL=(root) NOPASSWD: ${LIBEXEC}/database-access\$" \
      "${SUDOERS_FILE}"; then
      ok "sudoers rule names the configured operator and one program"
    else
      bad "${SUDOERS_FILE} does not name $(host_field ssh.operator_user) and ${LIBEXEC}/database-access"
      violations=$((violations + 1))
    fi
  else
    bad "${SUDOERS_FILE} is absent; bin/connect.sh cannot reach the access broker"
    violations=$((violations + 1))
  fi

  local unit
  for unit in agentic-postgres-docker-firewall.service agentic-postgres-edge.service \
              agentic-postgres-project@.service; do
    if [ -f "${SYSTEMD_DIR}/${unit}" ]; then
      ok "unit ${unit}"
    else
      bad "unit ${unit} is not installed"
      violations=$((violations + 1))
    fi
  done

  printf '\n== docker ==\n'
  # Reported as its own deviation rather than left to surface as a failed
  # `systemctl restart docker` later, which reads as a Docker problem rather
  # than as Docker being absent.
  if command -v docker >/dev/null 2>&1; then
    ok "docker $(docker --version 2>/dev/null | awk '{print $3}' | tr -d ,)"
  else
    bad "docker is not installed; --apply installs it from the official repository"
    violations=$((violations + 1))
  fi

  if docker compose version >/dev/null 2>&1; then
    ok "compose plugin $(docker compose version --short 2>/dev/null)"
  else
    bad "the Compose v2 plugin is absent; every script here invokes 'docker compose'"
    violations=$((violations + 1))
  fi

  if [ -f /etc/docker/daemon.json ]; then
    ok "daemon.json installed"
  else
    bad "daemon.json is not installed"
    violations=$((violations + 1))
  fi
  if ss -H -lnt 2>/dev/null | grep -qE ':(2375|2376)\b'; then
    bad "the Docker daemon is listening on TCP"
    violations=$((violations + 1))
  else
    ok "no Docker TCP socket"
  fi

  printf '\n== firewall ==\n'
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q 'Status: active'; then
    ok "ufw is active"
  else
    bad "ufw is not active"
    violations=$((violations + 1))
  fi
  if [ -f "${ETC}/docker-user-rules.v4" ]; then
    ok "DOCKER-USER policy rendered"
  else
    bad "DOCKER-USER policy is not rendered"
    violations=$((violations + 1))
  fi

  printf '\n== listeners ==\n'
  # Classification lives in agentic_postgres.listeners, not in awk, because the
  # thing being decided is "can a packet from off this host reach it" and the
  # bind address is the whole answer. Reading the port and discarding the
  # address reports systemd-resolved's 127.0.0.53 stub as an exposure, which is
  # how a check earns the right to be ignored.
  #
  # The socket list travels in the environment, not through a pipe. `python -`
  # reads its program from stdin, so piping `ss` into a heredoc invocation gives
  # stdin two claimants: the heredoc wins, Python never reads the pipe, `ss`
  # writes to a pipe with no reader and takes SIGPIPE, and under `pipefail` that
  # ends the script -- with no error, in the middle of a check, before the
  # deviation summary is printed. It did exactly that on the deployment host for
  # three runs before anyone noticed the summary line was missing.
  local unexpected listening
  listening="$(ss -H -lnt 2>/dev/null || true)"
  unexpected="$(
    APG_LISTENING_SOCKETS="${listening}" PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - \
      "${ssh_port}" 80 443 <<'PYTHON'
import os
import sys

from agentic_postgres.listeners import unexpected_public_ports

ports = unexpected_public_ports(
    os.environ["APG_LISTENING_SOCKETS"], (int(argument) for argument in sys.argv[1:])
)
print(" ".join(str(port) for port in ports))
PYTHON
  )"
  if [ -z "${unexpected}" ]; then
    ok "only ${ssh_port}, 80 and 443 listen on a public address"
  else
    bad "unexpected public listening ports: ${unexpected}"
    violations=$((violations + 1))
  fi

  printf '\n'
  if [ "${violations}" -eq 0 ]; then
    printf 'provision-host: the host meets the Session 2 baseline.\n'
    return 0
  fi
  printf 'provision-host: %d deviation(s).\n' "${violations}"
  return 6
}

# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

timer_is_armed() {
  systemctl list-timers "$1*" --all 2>/dev/null | grep -q "$1"
}

# Advisory. Being first in the include order beats a plain directive in a later
# file, but nothing beats a Match block, which applies wherever it appears. The
# authoritative answer is what sshd actually resolves, checked below; this exists
# so that when that check refuses, the operator can see what to go and look at.
report_conflicting_snippets() {
  local snippet found=0
  for snippet in /etc/ssh/sshd_config.d/*.conf; do
    [ -f "${snippet}" ] || continue
    [ "${snippet}" = "${SSH_SNIPPET}" ] && continue
    if grep -qiE '^[[:space:]]*Match[[:space:]]' "${snippet}"; then
      note "NOTE ${snippet} contains a Match block; it applies regardless of include order."
      found=1
    fi
  done
  return "${found}"
}

# Verify the merged configuration before reloading it, and undo it if it is
# wrong. `sshd -t` checks syntax; it has nothing to say about whether the policy
# that came out of the merge still lets the operator authenticate. Reloading
# first and discovering that from a failed login is what the rollback timer is
# for, and the timer is the last line of defence, not the first.
#
# -C resolves Match blocks the way sshd will for this operator's real
# connection. Without it a `Match User op` re-enabling password authentication,
# or worse disabling pubkey, is invisible here and decisive in production.
verify_resolved_sshd_policy() {
  local operator="$1" probe_address="$2" resolved pair missing=0

  if ! resolved="$(sshd -T -C "user=${operator},host=localhost,addr=${probe_address}" 2>/dev/null)"
  then
    # Older sshd, or criteria it will not accept. A plain -T still resolves the
    # global block, which is better than resolving nothing.
    note "NOTE sshd rejected the -C probe; falling back to the global resolution."
    resolved="$(sshd -T 2>/dev/null || true)"
  fi

  for pair in "${SSHD_REQUIRED_POLICY[@]}"; do
    printf '%s\n' "${resolved}" | grep -qi "^${pair}$" || {
      printf '  RESOLVED POLICY WRONG: expected %q\n' "${pair}" >&2
      missing=$((missing + 1))
    }
  done

  [ "${missing}" -eq 0 ]
}

rollback_is_armed() {
  timer_is_armed "${ROLLBACK_UNIT}"
}

ufw_rollback_is_armed() {
  timer_is_armed "${UFW_ROLLBACK_UNIT}"
}

render_templates() {
  local ssh_port public_interface
  ssh_port="$(host_field ssh.port)"
  public_interface="$(host_field host.public_interface)"

  # The schema permits 'auto'. Resolve it here rather than writing the literal
  # string into a firewall rule, where it would match no interface and the
  # policy would silently protect nothing.
  if [ "${public_interface}" = "auto" ]; then
    public_interface="$(ip -4 route show default | awk '{print $5}' | head -1)"
    [ -n "${public_interface}" ] \
      || die 3 "public_interface is 'auto' but no default route exists to resolve it from."
    note "resolved public_interface 'auto' to ${public_interface}"
  fi

  install -d -m 0755 -o root -g root "${ETC}"

  sed "s|__SSH_PORT__|${ssh_port}|g" \
    "${ROOT_DIR}/infra/host/00-agentic-postgres-ssh.conf" > "${ETC}/00-agentic-postgres-ssh.conf"

  local family
  for family in v4 v6; do
    sed "s|__PUBLIC_INTERFACE__|${public_interface}|g" \
      "${ROOT_DIR}/infra/host/docker-user-rules.${family}" \
      > "${ETC}/docker-user-rules.${family}"
  done

  install -m 0644 -o root -g root "${ROOT_DIR}/infra/host/daemon.json" "${ETC}/daemon.json"
  note "rendered templates into ${ETC}"
}

# The units name /usr/local/libexec/agentic-postgres/<name> and nothing else,
# so the launchers have to be there before any unit is enabled. Installed from
# the checkout deliberately: these are the *indirection*, not the code they
# resolve to, and they change only when the repository changes.
install_launchers() {
  install -d -m 0755 -o root -g root "${LIBEXEC}"

  # Named `origin` rather than `source`, which is a shell builtin and reads as
  # one to both a human and a grep.
  local origin name
  for origin in "${ROOT_DIR}"/libexec/agentic-postgres-*; do
    [ -f "${origin}" ] || continue
    # agentic-postgres-edge -> edge. The units invoke the short name; the long
    # name exists so the repository directory is self-describing.
    name="$(basename "${origin}")"
    name="${name#agentic-postgres-}"
    install -m 0755 -o root -g root "${origin}" "${LIBEXEC}/${name}"
  done

  note "installed $(find "${LIBEXEC}" -maxdepth 1 -type f | wc -l) launcher(s) into ${LIBEXEC}"
}

# The `sudo -n` rule bin/connect.sh reaches the broker through (ADR 0043).
#
# Written to a temporary file and checked with `visudo -cf` BEFORE it is
# installed. A syntactically invalid file in /etc/sudoers.d does not break one
# rule, it breaks sudo -- on a host whose only administrative path is sudo over
# SSH. That is a lockout with the same shape as the sshd one this script already
# arms a rollback timer for, and it is avoidable for the cost of one check.
#
# Mode 0440 because sudo refuses to read a file that is group- or
# world-writable, and refusing to read it is refusing every rule in it.
install_database_access_sudoers() {
  local operator="$1"
  command -v visudo >/dev/null 2>&1 || die 3 "visudo is not installed; refusing to write a sudoers file that cannot be checked."

  install -d -m 0755 -o root -g root /etc/sudoers.d

  local staging
  staging="$(mktemp)"
  {
    printf '# Managed by bin/provision-host.sh (ADR 0043). Do not edit by hand.\n'
    printf '#\n'
    printf '# One program, by a path that never changes. The trampoline resolves the\n'
    printf '# release a project was deployed through and hands over to that release,\n'
    printf '# which decides whether this account may have what it asked for.\n'
    printf '%s ALL=(root) NOPASSWD: %s/database-access\n' "${operator}" "${LIBEXEC}"
  } > "${staging}"

  if ! visudo -cf "${staging}" >/dev/null; then
    rm -f "${staging}"
    die 6 "the generated sudoers rule did not pass visudo; nothing was installed."
  fi

  install -m 0440 -o root -g root "${staging}" "${SUDOERS_FILE}"
  rm -f "${staging}"

  # Checked again in place, because what matters is that the whole of
  # /etc/sudoers parses with this file in it, not that the fragment did on its
  # own. An include that is individually valid can still collide.
  if ! visudo -c >/dev/null; then
    rm -f "${SUDOERS_FILE}"
    die 6 "sudo policy did not parse with ${SUDOERS_FILE} installed; it was removed."
  fi

  note "installed ${SUDOERS_FILE} for ${operator}"
}

# Docker comes from Docker's own apt repository, not from Ubuntu's.
#
# Ubuntu's docker.io package lags, and more importantly it does not ship the
# Compose v2 plugin, which every script here invokes as `docker compose`. The
# floor in versions.env (COMPOSE_MINIMUM_VERSION) is checkable only against a
# build that has it.
#
# The repository is added with a keyring file rather than apt-key, and the suite
# is verified to exist before it is written into sources.list.d. A missing suite
# otherwise turns into an `apt-get update` failure whose message is about a
# signature, not about a release Docker has not published yet.
install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    note "docker and the compose plugin are already installed"
    return 0
  fi

  local codename
  codename="$(grep -m1 '^VERSION_CODENAME=' /etc/os-release | cut -d= -f2- | tr -d '"')"
  [ -n "${codename}" ] || die 3 "could not read VERSION_CODENAME from /etc/os-release."

  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl >/dev/null

  # Confirm Docker actually publishes this release before trusting the repo.
  if ! curl -fsSL -o /dev/null "https://download.docker.com/linux/ubuntu/dists/${codename}/Release"; then
    die 3 "Docker publishes no apt suite for Ubuntu '${codename}' yet.
     This is a stop condition rather than something to work around: falling back to
     a different codename would install packages built for another release, and
     falling back to Ubuntu's docker.io would omit the Compose v2 plugin every
     script here depends on. Wait for the suite, or deploy on 24.04 (noble)."
  fi

  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc \
    || die 3 "could not fetch the Docker apt signing key."
  chmod a+r /etc/apt/keyrings/docker.asc

  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" "${codename}" > /etc/apt/sources.list.d/docker.list

  apt-get update -qq
  apt-get install -y -qq \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null \
    || die 3 "the Docker packages could not be installed."

  # The operator is deliberately NOT added to the docker group. Membership is
  # equivalent to root -- the socket will start any container with any mount --
  # so it would quietly undo the privilege boundary every script here maintains
  # by requiring explicit sudo.
  note "installed docker from the official repository for ${codename}"
  note "the operator is not in the docker group; that is deliberate and equals root"
}

# Install an immutable release from the operator checkout and record it.
#
# This is what makes the enabled units able to run at all. Both launchers
# resolve /etc/agentic-postgres/edge-state.json, refuse to continue without it,
# and execute out of /opt/agentic-postgres/releases/<commit> so systemd never
# runs a live checkout. Nothing wrote that file, so the firewall unit was
# enabled on a provisioned host and had never once executed: the DOCKER-USER
# policy existed only because --apply had run the reconciler from the checkout
# by hand, and a reboot would have left the chain empty.
#
# It belongs here rather than in deploy.sh because the firewall is a host
# concern that has to hold whether or not any project is deployed. Waiting for
# the first deployment to install a release means the host spends a whole run
# with an enabled unit that cannot start.
install_release() {
  local commit digest

  commit="$(
    PYTHONPATH="${ROOT_DIR}/src" "$(python_bin)" - "${ROOT_DIR}" "${HOST_MANIFEST}" <<'PYTHON'
import hashlib
import sys
from pathlib import Path

from agentic_postgres import edge_state, installed_release

checkout, manifest = Path(sys.argv[1]), Path(sys.argv[2])

# Archived from the commit, not copied from the tree: untracked files, editor
# state and a dirty index cannot reach a directory that runs as root.
commit = installed_release.resolve_commit(checkout)
installed_release.assert_clean(checkout)
installed_release.install(checkout, commit=commit)

edge_state.write_state(
    edge_state.build_state(
        installed_release_commit=commit,
        host_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
    )
)
print(commit)
PYTHON
  )" || die 6 "could not install a release from the checkout; see the error above."

  digest="${commit:0:12}"
  note "installed release ${digest} at /opt/agentic-postgres/releases/${commit}"
  note "recorded it in ${ETC}/edge-state.json, which the launchers resolve"
}

install_units() {
  local origin name
  for origin in "${ROOT_DIR}"/systemd/*.service; do
    [ -f "${origin}" ] || continue
    name="$(basename "${origin}")"
    install -m 0644 -o root -g root "${origin}" "${SYSTEMD_DIR}/${name}"
  done

  systemctl daemon-reload
  note "installed units into ${SYSTEMD_DIR}"

  # The firewall unit is enabled here because DOCKER-USER must be reconciled
  # after every docker.service start, including the one this script just did.
  # The edge and project units are NOT enabled: nothing is deployed yet, and a
  # unit that fails on every boot until Run 6 trains an operator to ignore it.
  systemctl enable agentic-postgres-docker-firewall.service >/dev/null 2>&1 \
    || die 6 "could not enable the firewall reconciliation unit."
  note "enabled agentic-postgres-docker-firewall.service"
  note "edge and project units installed but not enabled; Run 6 starts them"
}

apply_baseline() {
  local ssh_port
  ssh_port="$(host_field ssh.port)"

  # "Never two armed windows at once" (implementation plan §3). With both timers
  # armed, a failure gives no way to tell which change caused it, and the two
  # rollbacks can fire in either order.
  if rollback_is_armed && ufw_rollback_is_armed; then
    die 6 "both ${ROLLBACK_UNIT} and ${UFW_ROLLBACK_UNIT} are armed. Verify and disarm one first."
  fi

  install -d -m 0700 -o root -g root "${BACKUP_ROOT}"
  local stamp backup
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup="${BACKUP_ROOT}/${stamp}"
  install -d -m 0700 -o root -g root "${backup}"

  cp -a /etc/ssh "${backup}/ssh"
  iptables-save > "${backup}/iptables.v4" 2>/dev/null || true
  ip6tables-save > "${backup}/iptables.v6" 2>/dev/null || true
  note "backed up /etc/ssh and both iptables tables to ${backup}"

  render_templates

  # The host manifest becomes authoritative at /etc. Every later root operation
  # reads this copy, not whatever is in someone's checkout (plan divergence D22).
  install -m 0600 -o root -g root "${HOST_MANIFEST}" "${ETC}/host.yaml"

  printf '\n== launchers and units ==\n'
  # Before the SSH section, and this ordering is the point. The rollback timer
  # the operator must arm fires ssh-rollback out of ${LIBEXEC}, so that file has
  # to exist before there is anything to arm. On a fresh host the first --apply
  # therefore installs everything, skips SSH, and prints an arm command that now
  # names a file that is actually there; the second --apply does the hardening.
  install_launchers
  # After the launchers, because the rule names a file and a rule pointing at a
  # path that does not exist is one sudo accepts and nothing can use.
  install_database_access_sudoers "$(host_field ssh.operator_user)"
  # Before install_units, which enables the firewall unit. Enabling a unit whose
  # launcher cannot resolve a release is how an operator learns to ignore a
  # failing service.
  install_release
  install_units

  printf '\n== ssh ==\n'
  if rollback_is_armed; then
    local operator probe_address
    operator="$(host_field ssh.operator_user)"
    # The client address the probe pretends to come from. Any member of the
    # allowed set will do; the host's own public address is a real routable one,
    # which exercises an Address match the way a loopback address would not.
    probe_address="$(host_field host.expected_public_ipv4)"

    report_conflicting_snippets || true

    install -m 0644 -o root -g root "${ETC}/00-agentic-postgres-ssh.conf" "${SSH_SNIPPET}"
    sshd -t || {
      rm -f "${SSH_SNIPPET}"
      die 6 "sshd rejected the configuration; the snippet was removed and nothing was loaded."
    }

    # Written but not yet loaded. This is the last moment at which backing out
    # costs nothing, so it is where the resolved policy gets checked.
    verify_resolved_sshd_policy "${operator}" "${probe_address}" || {
      rm -f "${SSH_SNIPPET}"
      die 6 "the merged sshd policy is not what was asked for; snippet removed, nothing reloaded."
    }
    note "resolved sshd policy verified for ${operator}"

    # reload, never restart: restart drops every existing session, including the
    # one holding the door open.
    systemctl reload ssh || die 6 "sshd reload failed."
    note "SSH hardened. Open a NEW session with a key NOW and confirm it works."
    note "Then run: sudo ${ROOT_DIR}/bin/provision-host.sh --host ${HOST_MANIFEST} --confirm-ssh-ok"
  else
    printf '  SKIPPED SSH hardening: no rollback timer is armed.\n'
    printf '\n'
    printf '  Everything else is now installed, including the rollback launcher.\n'
    printf '  Arm the timer, confirm it shows a future trigger, then re-run --apply:\n\n'
    printf '    sudo systemd-run --on-active=10min --unit=%s \\\n' "${ROLLBACK_UNIT}"
    printf '      %s/ssh-rollback %s/ssh\n' "${LIBEXEC}" "${backup}"
    printf '    systemctl list-timers %s%s\n\n' "${ROLLBACK_UNIT}" "'*'"
    printf '  Keep your current session open. Do not close it until a NEW session works.\n'
  fi

  printf '\n== docker ==\n'
  install_docker
  install -d -m 0755 /etc/docker

  # Restart only when there is a reason to. --apply is meant to be re-runnable,
  # and from Run 6 onwards a restart takes the edge and every project down with
  # it -- so an unconditional `systemctl restart docker` turns "verify the
  # baseline is still met" into an outage. The daemon is restarted when its
  # configuration actually changed, or when it is not running.
  local daemon_changed=0
  cmp -s "${ETC}/daemon.json" /etc/docker/daemon.json || daemon_changed=1

  install -m 0644 -o root -g root "${ETC}/daemon.json" /etc/docker/daemon.json
  if command -v dockerd >/dev/null 2>&1; then
    dockerd --validate --config-file=/etc/docker/daemon.json \
      || die 6 "dockerd rejected /etc/docker/daemon.json; the previous file is in ${backup}."
  fi

  if [ "${daemon_changed}" -eq 1 ] || ! systemctl is-active --quiet docker; then
    systemctl restart docker || die 6 "docker failed to restart; see journalctl -u docker -n 200."
    note "docker restarted with the installed configuration"
  else
    note "docker configuration unchanged; not restarting"
  fi

  printf '\n== firewall ==\n'
  # Order is the control. The SSH allow rule goes in before default-deny, and
  # both before enable. A script that reaches `ufw enable` without an SSH rule
  # has locked the operator out, so it refuses to.
  #
  # Adding allow rules while ufw is inactive changes no packet's fate, so those
  # are unconditional. `enable` is the step that can strand an operator, and it
  # is gated on an armed rollback exactly as the SSH snippet is.
  ufw allow "${ssh_port}/tcp" >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null

  # `ufw show added`, not `ufw status`. While ufw is inactive, `status` prints
  # "Status: inactive" and lists nothing at all — so on the one host state where
  # this guard matters, reading `status` proves the SSH rule is missing no
  # matter how many times it was just added. `show added` reports the configured
  # rules, which is what will be in force the moment `enable` runs.
  #
  # The port is anchored on both sides: an unanchored 22 also matches 122/tcp.
  ufw show added 2>/dev/null | grep -qE "(^|[[:space:]])${ssh_port}/tcp([[:space:]]|\$)" \
    || die 6 "no rule covers the SSH port; refusing to enable the firewall."

  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null

  if ufw status 2>/dev/null | grep -q 'Status: active'; then
    # Already enforcing. Re-running is not a new window and must not demand a
    # timer, or every idempotent re-apply becomes a two-step ceremony.
    note "ufw is already active; rules reconciled"
  elif ufw_rollback_is_armed; then
    ufw --force enable >/dev/null
    note "ufw enabled with ${ssh_port}, 80 and 443 permitted"
    note "Open a NEW session NOW and confirm it works."
    note "Then run: sudo ${ROOT_DIR}/bin/provision-host.sh --host ${HOST_MANIFEST} --confirm-firewall-ok"
  else
    printf '  SKIPPED enabling ufw: no firewall rollback timer is armed.\n'
    printf '\n'
    printf '  The allow rules for %s, 80 and 443 are in place but not enforcing.\n' "${ssh_port}"
    printf '  Arm the timer, confirm it shows a future trigger, then re-run --apply:\n\n'
    printf '    sudo systemd-run --on-active=10min --unit=%s \\\n' "${UFW_ROLLBACK_UNIT}"
    printf '      /usr/sbin/ufw --force disable\n'
    printf '    systemctl list-timers %s%s\n\n' "${UFW_ROLLBACK_UNIT}" "'*'"
    printf '  Keep your current session open until a NEW one connects.\n'
  fi

  "${ROOT_DIR}/bin/docker-firewall.sh" reconcile
  systemctl enable --now unattended-upgrades.service >/dev/null 2>&1 || true

  printf '\n'
  check_baseline
}

main() {
  parse_arguments "$@"

  if [ "${CONFIRM_SSH_OK}" -eq 1 ] && [ "${CONFIRM_FIREWALL_OK}" -eq 1 ]; then
    die 2 "confirm one rollback at a time; they attest to two different things."
  fi

  if [ "${CONFIRM_SSH_OK}" -eq 1 ]; then
    [ "$(id -u)" -eq 0 ] || die 3 "--confirm-ssh-ok requires root."
    systemctl stop "${ROLLBACK_UNIT}.timer" 2>/dev/null || true
    systemctl reset-failed "${ROLLBACK_UNIT}.service" 2>/dev/null || true
    printf 'provision-host: SSH rollback disarmed.\n'
    return 0
  fi

  if [ "${CONFIRM_FIREWALL_OK}" -eq 1 ]; then
    [ "$(id -u)" -eq 0 ] || die 3 "--confirm-firewall-ok requires root."
    systemctl stop "${UFW_ROLLBACK_UNIT}.timer" 2>/dev/null || true
    systemctl reset-failed "${UFW_ROLLBACK_UNIT}.service" 2>/dev/null || true
    printf 'provision-host: firewall rollback disarmed.\n'
    return 0
  fi

  [ "$(id -u)" -eq 0 ] || die 3 "must run as root."

  cd "${ROOT_DIR}"
  case "${MODE}" in
    check) check_baseline ;;
    apply) apply_baseline ;;
  esac
}

main "$@"

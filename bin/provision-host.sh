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
readonly BACKUP_ROOT="/var/backups/agentic-postgres"
readonly SSH_SNIPPET="/etc/ssh/sshd_config.d/00-agentic-postgres-ssh.conf"
readonly ROLLBACK_UNIT="apg-ssh-rollback"

MODE="check"
HOST_MANIFEST=""
CONFIRM_SSH_OK=0

usage() {
  cat <<'USAGE'
Usage: sudo bin/provision-host.sh --host FILE [--check | --apply]
       sudo bin/provision-host.sh --host FILE --confirm-ssh-ok

  --check   Report every deviation from the Session 2 baseline and change
            nothing. This is the default.
  --apply   Bring the host to the baseline.
  --confirm-ssh-ok
            Disarm the SSH rollback timer. Run this only after opening a NEW
            SSH session with a key and confirming it works. It is separate on
            purpose: a script that cancelled its own rollback would cancel it
            in exactly the case where the script was wrong.

  --host FILE  The host manifest.

Before --apply hardens SSH it requires a rollback timer to already be armed:

  sudo systemd-run --on-active=10min --unit=apg-ssh-rollback \
    /usr/local/libexec/agentic-postgres/ssh-rollback <backup-dir>

If a new session fails after hardening, do nothing for ten minutes and let the
timer restore the previous configuration.
USAGE
}

die() {
  local code="$1"
  shift
  printf 'provision-host: %s\n' "$*" >&2
  exit "$code"
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
}

host_field() {
  PYTHONPATH="${ROOT_DIR}/src" python - "${HOST_MANIFEST}" "$1" <<'PYTHON'
import sys
from pathlib import Path

from agentic_postgres.host_config import load_host_manifest

value = load_host_manifest(Path(sys.argv[1]))["host"]
for part in sys.argv[2].split("."):
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

  # shellcheck disable=SC1091
  . /etc/os-release
  case "${VERSION_ID-}" in
    24.04|26.04) ok "Ubuntu ${VERSION_ID}" ;;
    *) bad "Ubuntu ${VERSION_ID-unknown} is not a supported release"; violations=$((violations + 1)) ;;
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
    for pair in "permitrootlogin no" "passwordauthentication no" "pubkeyauthentication yes"; do
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

  printf '\n== docker ==\n'
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
  local unexpected
  unexpected="$(ss -H -lnt 2>/dev/null \
    | awk '{print $4}' \
    | sed 's/.*://' \
    | sort -u \
    | grep -vE "^(${ssh_port}|80|443)$" || true)"
  if [ -z "${unexpected}" ]; then
    ok "only ${ssh_port}, 80 and 443 are listening"
  else
    bad "unexpected listening ports: $(printf '%s' "${unexpected}" | tr '\n' ' ')"
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

rollback_is_armed() {
  systemctl list-timers "${ROLLBACK_UNIT}*" --all 2>/dev/null | grep -q "${ROLLBACK_UNIT}"
}

render_templates() {
  local ssh_port public_interface
  ssh_port="$(host_field ssh.port)"
  public_interface="$(host_field network.public_interface)"

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

apply_baseline() {
  local ssh_port
  ssh_port="$(host_field ssh.port)"

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

  printf '\n== ssh ==\n'
  if rollback_is_armed; then
    install -m 0644 -o root -g root "${ETC}/00-agentic-postgres-ssh.conf" "${SSH_SNIPPET}"
    sshd -t || die 6 "sshd rejected the configuration; the snippet was written but not loaded."
    # reload, never restart: restart drops every existing session, including the
    # one holding the door open.
    systemctl reload ssh || die 6 "sshd reload failed."
    note "SSH hardened. Open a NEW session with a key NOW and confirm it works."
    note "Then run: sudo bin/provision-host.sh --host ${HOST_MANIFEST} --confirm-ssh-ok"
  else
    printf '  SKIPPED SSH hardening: no rollback timer is armed.\n'
    printf '  Arm one, then re-run --apply:\n'
    printf '    sudo systemd-run --on-active=10min --unit=%s \\\n' "${ROLLBACK_UNIT}"
    printf '      /usr/local/libexec/agentic-postgres/ssh-rollback %s/ssh\n' "${backup}"
  fi

  printf '\n== docker ==\n'
  install -d -m 0755 /etc/docker
  install -m 0644 -o root -g root "${ETC}/daemon.json" /etc/docker/daemon.json
  if command -v dockerd >/dev/null 2>&1; then
    dockerd --validate --config-file=/etc/docker/daemon.json \
      || die 6 "dockerd rejected /etc/docker/daemon.json; the previous file is in ${backup}."
  fi
  systemctl restart docker || die 6 "docker failed to restart; see journalctl -u docker -n 200."
  note "docker restarted with the installed configuration"

  printf '\n== firewall ==\n'
  # Order is the control. The SSH allow rule goes in before default-deny, and
  # both before enable. A script that reaches `ufw enable` without an SSH rule
  # has locked the operator out, so it refuses to.
  ufw allow "${ssh_port}/tcp" >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null

  ufw status | grep -q "${ssh_port}/tcp" \
    || die 6 "no rule covers the SSH port; refusing to enable the firewall."

  ufw default deny incoming >/dev/null
  ufw default allow outgoing >/dev/null
  ufw --force enable >/dev/null
  note "ufw enabled with ${ssh_port}, 80 and 443 permitted"

  "${ROOT_DIR}/bin/docker-firewall.sh" reconcile
  systemctl enable --now unattended-upgrades.service >/dev/null 2>&1 || true

  printf '\n'
  check_baseline
}

main() {
  parse_arguments "$@"

  if [ "${CONFIRM_SSH_OK}" -eq 1 ]; then
    [ "$(id -u)" -eq 0 ] || die 3 "--confirm-ssh-ok requires root."
    systemctl stop "${ROLLBACK_UNIT}.timer" 2>/dev/null || true
    systemctl reset-failed "${ROLLBACK_UNIT}.service" 2>/dev/null || true
    printf 'provision-host: SSH rollback disarmed.\n'
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

# Host baseline

What a Session 2 deployment host is, how it gets that way, and what is
deliberately left unmeasured. Cited by `Documentation=` in
`agentic-postgres-edge.service` and
`agentic-postgres-docker-firewall.service`, so it is the first thing
`systemctl status` points an operator at.

The authority is `bin/provision-host.sh`, and `--check` is its default. Nothing
below is aspirational: each line is either applied by that script or reported by
it as a deviation.

## The shape of the baseline

| Area | Policy | Where it comes from |
|---|---|---|
| SSH | Key-only. `PermitRootLogin no`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `MaxAuthTries 3`. **Source addresses are not restricted** — see below. | `infra/host/00-agentic-postgres-ssh.conf` → `/etc/ssh/sshd_config.d/` |
| Firewall | UFW default-deny inbound; the configured SSH port, 80 and 443 allowed. | `bin/provision-host.sh` |
| Container ingress | A `DOCKER-USER` policy that matches the **pre-DNAT** destination port and ends in a drop, so a published container port is not a public one. | `infra/host/docker-user-rules.v{4,6}` → `/etc/agentic-postgres/`, applied by `bin/docker-firewall.sh` |
| Docker daemon | No TCP socket. Local socket only, read through an allowlisting proxy by anything public-facing. | `infra/host/daemon.json` |
| Patching | `unattended-upgrades` enabled, and configured **not** to reboot itself. | `infra/host/20auto-upgrades` |
| Releases | systemd runs `/opt/agentic-postgres/releases/<commit>/`, root-owned and immutable, through a launcher in `/usr/local/libexec/agentic-postgres/`. Never a checkout. | `bin/provision-host.sh`, `libexec/` |

**`ssh.allowed_source_cidrs` restricts nothing, and this table said otherwise
until Session 11 Run 8** (D661). The field is schema-required, CIDR-validated and
reported on — and it reaches no firewall rule and no sshd directive:
`provision-host.sh` runs `ufw allow <port>/tcp` with no source, and the snippet
carries no `Match Address` block. It is a **declared intent**, kept explicit in
the manifest so that `0.0.0.0/0` is a written choice rather than an omission.

The code has always said so; only this page did not. `host_config.py`:

> the controls that actually carry the SSH boundary are key-only authentication,
> `PermitRootLogin no` and `MaxAuthTries`, all of which the live-host suite
> asserts against `sshd -T`.

And the boundary is those controls as **OpenSSH actually resolves them** —
`sshd -T` for the real operator tuple, not what our snippet says, because OpenSSH
takes the first obtained value across a lexicographic include order and `Match`
blocks override regardless of position.

## Before the three passes: the operator account

`provision-host.sh` names `ssh.operator_user` in a sudoers rule and uses it as
the `sshd -T` probe — and **does not create it**. Pass 2 installs
`PermitRootLogin no`, so on a fresh host where root is the only login, pass 2
removes the only way in. Create the operator and **prove it works while root
still does**; the procedure is step 0 of the
[Session 2 operator guide](session-02-operator-guide.md).

Measured on a fresh Ubuntu 26.04 host in Session 11 Run 8: after pass 2, `ssh
root@host` is refused. The rollback timer is what stands between that and a dead
machine, which is exactly what it is for.

## Why a fresh host takes three `--apply` passes

Two steps can lock you out of your own server, and each refuses to run until its
own rollback timer is armed. Only one timer may be armed at a time, so the two
unverified windows never overlap.

1. `--apply` — installs launchers, units and Docker. Skips both locking steps
   and prints the exact command to arm the next one.
2. Arm `apg-ssh-rollback`, `--apply`, **open a new SSH session and confirm it
   works**, then `--confirm-ssh-ok`.
3. Arm `apg-ufw-rollback`, `--apply`, **open a new session through the enabled
   firewall**, then `--confirm-firewall-ok`.

Nothing is disarmed automatically, and the script never cancels its own
rollback. A script that did would cancel it in exactly the case where the script
was wrong. If a new session fails after either step, **do nothing for ten
minutes** and let the timer undo it.

## Running the gates on this host

Both gates run here, and each needs a different half of the operator's PATH:

```bash
sudo bin/session-02-check.sh --mode host --host host.yaml \
  --project-a-outputs /etc/agentic-postgres/projects/<a>/outputs.json \
  --project-b-outputs /etc/agentic-postgres/projects/<b>/outputs.json \
  --sentinel-file <path from the active generation>

sudo -u op bash -lc 'cd ~/agentic-postgres && . .venv/bin/activate && bin/session-01-check.sh'
```

The second line is not decoration. `bin/session-01-check.sh` needs **both**:

- `~/.local/bin` — `uv`, `shellcheck`, `jq`; reached by `bash -l` sourcing
  `.profile`
- `.venv/bin` — `python`, `ruff`, `pytest`; reached only by activating

`bash -lc` alone fails on the bare `python`; activating alone fails on
`uv is not installed`. It has always worked by hand because an operator's
interactive shell already has both.

Run it as the operator, not as root: the gate is non-mutating, and running it
under `sudo` leaves root-owned artifacts in a checkout that `op` has to keep
clean for the gate's own step 1.

`bin/lock-dev-deps.sh --check` runs `uv pip compile`, so **the Session 1 gate
requires PyPI egress from wherever it runs**, including this host.

## Accepted deviations

These are choices, recorded so they stay choices rather than becoming
assumptions.

**`ssh.allowed_source_cidrs: 0.0.0.0/0`.** An operator with no static source
address may write this. The field stays required and non-empty so the choice is
explicit in the manifest rather than an omission, and `--check` reports it as a
deviation on every run.

**IPv6 ingress is not measured from outside.** The host holds a global IPv6
address. No AAAA record is published, and no network available to run
`--mode external` from has IPv6 transit, so the external port scan
(`test_no_service_port_is_publicly_reachable_over_ipv6`) skips rather than
passes. What *is* measured, host-side:

- nothing binds a public IPv6 address except SSH —
  `test_only_ssh_and_the_edge_listen_on_a_public_address` parses `ss -lntup`,
  which covers both address families;
- `net.ipv6.conf.all.forwarding = 0`, so nothing is forwarded to a container
  over IPv6 at all;
- ufw is built with `IPV6=yes`, so the policy applies to both families;
- Traefik binds `0.0.0.0:443`, so there is no IPv6 ingress to the edge either.

The residual gap is therefore narrow and named: **no scan from the public
internet has confirmed the IPv6 address behaves as the host-side facts predict.**
It is recorded as divergence D35 rather than absorbed, and it is why no
`public_boundary` claim exists in `evidence/session-02.json` (ADR 0025). Publish
an AAAA record only when IPv6 ingress genuinely works — a published AAAA with
broken routing fails ACME HTTP-01 in a way that looks like a certificate problem
and is not one.

## Stop conditions

Do not work around these.

1. **Lockout.** A new SSH session fails after reload *and* the timed rollback
   does not restore. Use the provider console, restore from
   `/var/backups/agentic-postgres/`, and do not touch the firewall until SSH is
   proven from a fresh session.
2. **The socket proxy needs `privileged: true`, or Traefik needs an API section
   outside the allowlist.** Halt. Never grant privileged mode, and never mount
   the Docker socket into Traefik "temporarily".
3. **The `env -i` allowlist proves insufficient.** Extend it per variable with a
   written reason. Never `env -u`, never `sudo -E`.
4. **The host is not x86_64.** Halt. Every locked digest is wrong; that is a
   `versions.in.yaml` change and a full re-lock, not a runtime accommodation.

## See also

- [Provider bootstrap](provider-bootstrap.md)
- [Project isolation](project-isolation.md)
- [Secret handling](secret-handling.md)
- [Session 2 operator guide](session-02-operator-guide.md)
- [ADR 0009 — host configuration is separate, and one edge plane is shared](decisions/0009-host-and-edge-plane.md)
- [ADR 0018 — a check that cannot reach the daemon reports that, not a verdict](decisions/0018-daemon-access-is-not-a-verdict.md)

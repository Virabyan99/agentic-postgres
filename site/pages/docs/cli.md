---
title: The command-line client
description: apg, installed from PyPI as agentic-postgres-cli.
ledger: [cli_remote, management_api, accounts]
---
# The command-line client

`apg` acts through the management API only, as you. Install it with either:

```
pipx install agentic-postgres-cli
uv tool install agentic-postgres-cli
```

It needs Python 3.11 or newer and nothing else. `apg --version` names the release it was built for.

## Signing in

```
apg login password --endpoint https://control.agenticpostgresql.com/api/v1 --username NAME --totp-code-stdin
```

It asks for your password, and reads the six-digit code from standard input when your account has a second factor. A password, a key or a code is read from a prompt or a file only you can read, never from an argument. `apg logout` ends the session.

## The families

| Command | What it does |
|---|---|
| `apg login password`, `key`, `accept`, `totp-enroll`, `totp-confirm` | sign in, accept an invitation, set up the second factor |
| `apg context show` | the endpoint, organisation and project the next command uses |
| `apg org list`, `create`, `use`, `members`, `invite`, `set-role`, `remove`, `keys`, `key-create`, `key-revoke` | organisations, members, invitations and keys |
| `apg project list`, `use`, `show`, `create`, `claim`, `status`, `sleep`, `wake`, `delete`, `export`, `backups`, `idle-sleep` | projects |
| `apg compute get`, `set` | a project's compute size |
| `apg endpoint show`, `credential`, `connect` | the two doors and their passwords |
| `apg operation show`, `list`, `wait`, `cancel` | follow what you started |
| `apg branch create`, `reset`, `delete`, `list`, `show` | branches and restores |
| `apg plan list`, `show`, `notify-me` | plans |
| `apg usage show` | usage readings |
| `apg notifications list` | notifications |
| `apg insights show` | Query Insights |
| `apg monitoring show` | monitoring readings |

Most commands take `--json` for a machine-readable answer. A command that starts an operation prints its id; `apg operation wait --operation ID` follows it to the end.

## Exit codes

| Code | Means |
|---|---|
| 0 | done |
| 2 | the command line is wrong; nothing was sent |
| 3 | something the command needs is missing: a session, a chosen organisation, a file only you can read |
| 5 | the server refused; the refusal's word is printed |
| 6 | the server could not be reached, or a reading could not be determined |
| 7 | `wait` stopped at its own timeout; the operation continues |

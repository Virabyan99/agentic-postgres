# Secret handling

Where a secret value goes, how far it travels, and how "it did not leak" is
measured rather than asserted.

## The path

```
Infisical control-plane credential                    /root/.config/…, 0400 root
  → bin/bootstrap-providers.sh reads it by file descriptor
  → creates the project runtime machine identity and one Universal Auth
    client secret
  → /etc/agentic-postgres/credentials/<key>/infisical-client-{id,secret}   0400 root
  → bin/materialize-secrets.sh reads both files
  → POST /api/v1/auth/universal-auth/login over TLS
  → short-lived access token, PROCESS MEMORY ONLY
  → GET /api/v3/secrets/raw/<key>?expandSecretReferences=false&includeImports=false
  → value in memory
  → /var/lib/agentic-postgres/secrets/<key>/generations/<gen>/<service>/<file>
      mode 0400, owned by the declared consumer uid:gid
  → fsync the file and the directory
  → atomic replace of active-secret-generation.json
  → the root-owned runtime override declares
      secrets: session2_sentinel: {file: <that exact immutable path>}
  → Compose mounts it at /run/secrets/session2_sentinel in that service ONLY
```

A generation is written complete, fsynced, and then made active by an atomic
rename. A container can never observe a half-written generation. Ownership and
mode are set by the host **before** Compose mounts the file; Compose's own
`uid`/`gid`/`mode` fields are not relied upon.

## What is and is not claimed

Secret-zero is **not** eliminated, and Session 2 does not claim it is. The
control-plane credential and one per-project client secret live on the host,
root-only. What Session 2 bounds is how far they travel.

## The declared grant surface

`secrets.required.yaml` is committed and contains identifiers only — names,
provider keys, paths, target filenames, numeric ownership. No value, and no hash
of one. Adding either would make the repository a place where a credential can
be recovered.

A service receives exactly the files listed for it there and nothing else.
Adding a grant is a reviewable diff rather than a runtime accident, and
`tests/contract/test_secret_contract.py` proves the Compose model and that file
agree **in both directions**.

The source path is derived from the project key by the materializer and cannot
be supplied from `project.yaml`. A project manifest that could name its own
secret directory could name another project's.

## Leak surfaces, and the test that catches each

| Surface | Control | Test |
|---|---|---|
| Source control | value never written into the tree; operator inputs gitignored | `test_the_sentinel_is_absent_from_every_git_visible_file` (scans `git ls-files` **and** `git ls-files -o`) |
| Compose interpolation | no `environment:` entry sourced from a secret; env-file key sets are exact | `test_no_service_takes_a_secret_through_the_environment` |
| `docker compose config` | the model references file paths, never values | `test_the_sentinel_is_absent_from_resolved_compose_output` |
| Process arguments | credentials read from files, never argv | `test_no_script_passes_a_secret_in_arguments` — static scan for `--client-secret`, `--token`, `KEY=… docker compose`, `infisical export`, `eval "$(`, `source *secret*` |
| Shell history / `set -x` | `set +x` as the **first executable line** of every credential-handling script | `test_secret_sections_disable_tracing` |
| `--env-file` | the wrapper's env-file set is fixed and disjoint three ways; no dotenv is ever generated | `test_no_dotenv_exists_under_the_secret_root` |
| systemd journal | scripts print fixed strings; `secret-check` prints a fixed success message, never the value or a digest | leak scan over `journalctl -u 'agentic-postgres-*'` |
| `docker inspect` | value never in a label, env, or command | `test_the_sentinel_is_absent_from_container_inspection` |
| Image layers | build runs with BuildKit network disabled and consumes no build secrets | `test_the_sentinel_is_absent_from_image_history` (`docker history --no-trunc`) |
| Container logs | — | `test_the_sentinel_is_absent_from_container_logs` |
| Traefik access log | `queryParameters.defaultMode: drop`, `headers.defaultMode: drop` | live: send `?apg_sentinel=<random>` and assert it is absent from a log known to be recording the request |
| Evidence files | the evidence schema forbids secret-bearing keys | leak scan over `evidence/` |
| Both `outputs.json` kinds | `assert_output_is_secret_free` on rendered **and** deployed | `test_output_schema.py` plus a deployed-branch variant |
| The scanner itself | prints path and object identifiers only | `test_the_scan_would_find_a_planted_value_and_would_not_print_it` |

`set +x` is the first executable line of `bin/bootstrap-providers.sh` and
`bin/materialize-secrets.sh` because `SHELLOPTS=xtrace` is honoured from bash
startup. Anything above that line would be traced to stderr.

## The sentinel

Session 2 materializes exactly one secret, and it exists to be proved rather
than used. `APG_SESSION2_SENTINEL` is a random 32+ byte value created by
bootstrap. The live suite reads it through a root-only helper into memory and
searches for the **exact byte sequence** everywhere a leak would land.

It never echoes what it matched, and never prints a digest of it either — a
digest of a low-entropy secret is a checkable guess.

The guard-the-guard test plants the sentinel in a temporary file and asserts the
scanner reports the path and never the value. A scanner that found nothing
because it was looking for the wrong bytes would otherwise report success
forever.

## Isolation is proved by the mount list, not by digests

`test_only_the_granted_service_mounts_a_secret` and
`test_no_container_mounts_another_projects_secret_directory` read the mount
list. A digest comparison would show that two projects hold different bytes; it
would not show that neither *could* read the other's file, which is the actual
claim.

## Rotation, and the stop condition

Rotation is by replacement: a new generation is written and made active
atomically. Nothing edits a materialized file in place.

**If the leak scanner finds the sentinel anywhere:** halt. Rotate the client
secret *and* the sentinel, fix the leak, and re-run from a clean generation. Do
not add the path to an exclusion list.

## Evidence

`evidence/session-02.json` records `tests.secret_leakage`, resolved from the
JUnit results of every node ID the acceptance registry lists for
`SEC-SECRET-001` and `SEC-SECRET-002`. A proof that was skipped, or one the
artifact does not contain, is not a pass — see
[ADR 0025](decisions/0025-evidence-names-the-claim-not-the-suite.md).

## See also

- [Provider bootstrap](provider-bootstrap.md)
- [Project isolation](project-isolation.md)
- [ADR 0008 — sensitive key detection by terminal token, never substring](decisions/0008-sensitive-key-policy.md)
- [ADR 0010 — secrets are individual files in immutable generations](decisions/0010-secret-materialization.md)
- [ADR 0013 — Compose wrapper scopes, the runtime gate, and three env files](decisions/0013-compose-wrapper-scopes.md)

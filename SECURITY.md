# Security

ForgeFlow runs model-generated code and can write to GitHub, so its design assumes that model
output, repository content, issues, pull requests and chat messages are all untrusted.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's "Report a vulnerability" (security
advisories) on this repository rather than in a public issue. Include reproduction steps and the
affected version or commit.

## Threat model and controls

| Threat | Control |
| --- | --- |
| Generated code harms the host | Commands run only in a sandbox: per-command Docker containers (`--network none`, read-only root, `--cap-drop ALL`, `no-new-privileges`, non-root user, CPU/memory/PID limits) or the Compose `sandbox-runner` on an internal-only network. The local subprocess sandbox refuses model-generated code unless `FORGEFLOW_ALLOW_UNSAFE_LOCAL_SANDBOX=true`. |
| Arbitrary command execution | Models never supply commands. Agents use verification profiles detected from the repository, and every argv is checked against an allowlist (`security/command_policy.py`); no shell is ever invoked. Dependency installation is off by default. |
| Credential exposure | Workspaces receive source tarballs pinned to a commit, never tokens or git remotes. Sandboxes receive no host environment. Secrets are `SecretStr` and never returned by the API. Logs, events, tool arguments and memory are passed through `security/redaction.py`. The web UI talks to the API through a server-side proxy; tokens are not shipped to browsers. |
| Prompt injection | Untrusted content is fenced with per-call random delimiters and a policy stating it cannot change instructions. Outputs are validated against strict Pydantic schemas. Edits are validated (paths, protected files, file limits) independently of the model. Injection-like phrases are flagged in review. Nothing consequential happens without human approval. |
| Unauthorized external writes | GitHub writes happen only in the Pull Request agent after an approval recorded in the database, only to `forgeflow/*` branches, as draft pull requests, and never by force-updating a branch. Protected branches are never written. |
| Path traversal / symlink escape | Repository-relative paths are validated; every write is resolved and checked against the workspace root; symlinks and special files are dropped when workspaces are created. |
| Slack spoofing / replay | HMAC-SHA256 signature and 5-minute timestamp window, per-user role mapping from server config, strict command grammar, delivery de-duplication. Free-text mentions never start work. |
| Abuse of the API | Bearer-token authentication (hashed at rest), viewer/operator/admin roles, per-principal rate limiting, structured audit log for state-changing actions. |
| Runaway executions | Per-node and per-execution timeouts, bounded debugging attempts, cancellation, stall detection. |

## Least-privilege GitHub access

Use a fine-grained personal access token or a GitHub App installed on selected repositories with:
Contents (read/write), Pull requests (read/write), Issues (read), Checks and Commit statuses
(read). ForgeFlow does not need administration, workflow or secrets permissions, and it refuses to
edit `.github/` files.

## Known limitations

- The local sandbox is not an isolation boundary; use `docker` or `runner` mode for real models.
- The sandbox image ships a Python toolchain. Repositories that need other toolchains or
  dependency installation require a custom sandbox image.
- Prompt-injection defenses reduce risk but cannot eliminate it; the approval gate and code-level
  validation are the controls that must hold.

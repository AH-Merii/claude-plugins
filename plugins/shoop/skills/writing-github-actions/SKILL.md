---
name: writing-github-actions
description: How to set up, change, speed up and secure GitHub Actions CI. Covers a baseline every workflow meets (a read-only token granted per job, actions pinned to commit SHAs, concurrency, timeouts, no expression injection), required checks that report on every pull request (path filters leave them pending; a job skipped by an `if:` that fails closed reports success), measuring step timings before optimising, caches and their limits, sharding slow suites, and verifying with actionlint, zizmor and a real run. Use when creating or editing anything under .github/workflows/ or an action.yml, when a required check sits at "Waiting for status to be reported", when CI is slow or its cache is full, or when reviewing a workflow's permissions, triggers or pinned actions.
---

# Writing GitHub Actions

A workflow runs code with the repository's token, and a required check gates every merge. Make both safe and reliable first, then make CI fast, from measurements.

## Before you edit

- **Read what's already there.** That means the other workflows, `.github/dependabot.yml`, CODEOWNERS and any check tasks the workflows call. Match their conventions: runner labels, how actions are pinned, how jobs are named.
- **Treat a required check's name as a contract.** Branch protection or a ruleset names the check, and the check takes its name from the job's `name:`, or its id when there is no `name:`. Keep that job's name when you restructure. For example, "main: test must pass" requires the job named `test` ([nvim-config D148](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#d148-ci-skips-what-it-doesnt-need-2026-10-19)).
- **Look up action versions; never recall them.** A SHA written from memory is either invalid or points at something else. Resolve the latest release and its commit ([konstruktoid](https://github.com/konstruktoid/agent-instructions-skills/tree/main/skills/github/github-actions-security)):

  ```sh
  gh api repos/actions/checkout/releases/latest --jq .tag_name   # e.g. v7.0.1
  gh api repos/actions/checkout/commits/v7.0.1 --jq .sha
  ```

## Baseline for every workflow you touch

- **`permissions: {}` at the top, scopes granted per job.** Once any scope is listed, every unlisted one is set to `none` ([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#permissions)). Granting per job keeps a write scope out of the jobs that run pull request code.
- **Pin every action to a full commit SHA with the version in a comment:** `uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1`. A tag can be moved: the tj-actions/changed-files compromise in March 2025 repointed existing tags at a malicious commit (security reference).
- **Set `persist-credentials: false` on `actions/checkout`** unless a later step pushes with that token. Otherwise the token stays in `.git/config` for every later step.
- **Never put `${{ }}` inside `run:`.** The runner pastes the value into the script before the shell parses it, so a pull request title can run commands. Pass values through `env:` and quote them:

  ```yaml
  - run: bash .github/changed-inputs.sh "$EVENT" "$BEFORE"
    env:
      EVENT: ${{ github.event_name }}
      BEFORE: ${{ github.event.before }}
  ```

- **Set `timeout-minutes` on every job.** The default is 360 ([workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes)), so a hung job can burn six hours.
- **Cancel superseded pull request runs.** Use a concurrency group per workflow and ref, since groups are shared by every workflow in the repository ([concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)). Don't cancel runs that deploy, publish or write shared state, such as main's cache writes. Serialise those in a group without cancellation instead.

  ```yaml
  concurrency:
    group: ${{ github.workflow }}-${{ github.ref }}
    cancel-in-progress: ${{ github.event_name == 'pull_request' }}
  ```

- **Keep pins current with Dependabot** for the `github-actions` ecosystem, with a cooldown of about a week before new releases are adopted (security reference).

## Required checks must always report

- **Never put `paths:` or `paths-ignore:` on the trigger of a workflow whose job is a required check.** When the filter skips the workflow, the check stays "Pending" and blocks the merge ([GitHub: handling skipped but required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks)).
- **To skip work, skip the job with `if:`. A job skipped by its `if:` reports "Success".**
- **Fail closed.** If the job that decides whether to skip fails, its outputs are empty and the required job must still run. Without a status function, GitHub adds `success()`, so the required job is skipped and goes green (same page). Skip only on an explicit "no":

  ```yaml
  if: ${{ !cancelled() && needs.changes.outputs.tests != 'false' }}
  ```

- **Name an aggregator job after the required check when the work is split** across a matrix or several jobs. Each matrix leg reports its own check. The aggregator runs under `always()` or `!cancelled()` and fails unless every result it needs is a success.

Patterns, a changed-files script and the rejected alternatives are in [references/required-checks.md](references/required-checks.md).

## Measure before optimising

- **Get per-step times from real runs, several of them.** One run hides the variance: the same job took 413 to 585 s across 9 runs ([D148](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#d148-ci-skips-what-it-doesnt-need-2026-10-19)).

  ```sh
  gh run view <run-id> --json jobs --jq '.jobs[] | .name as $j | .steps[] |
    [$j, .name, ((.completedAt|fromdate) - (.startedAt|fromdate))] | @tsv'
  ```

- **Check each step's premise against the log.** A "Free disk space" step took 47 to 119 s per run to make room the runner already had. The docs list 14 GB of storage, but `df -h /` showed 86 GB free ([runner specs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners), run 39290079036 in D148).
- **Optimise the time to a verdict:** from the run's creation to the end of the job that decides pass or fail, not one step's time ([nvim-config#86](https://github.com/AH-Merii/nvim-config/pull/86#issuecomment-6273802303)).

## Where to go next

| The change | Read |
| --- | --- |
| A required check, skipping work by changed files, an aggregator job, `merge_group` | [references/required-checks.md](references/required-checks.md) |
| CI is slow: dropping steps, skipping runs, sharding a suite, tests that wait on fixed timeouts | [references/speed.md](references/speed.md) |
| `actions/cache`, setup-action caches, Docker layer caches, the 10 GB limit, pruning | [references/caching.md](references/caching.md) |
| Triggers on fork code (`pull_request_target`, `workflow_run`, comments), secrets, OIDC, write scopes, Dependabot, cache poisoning | [references/security.md](references/security.md) |

The [assets/](assets/) folder holds files to copy into a repository and adapt: [changed-inputs.sh](assets/changed-inputs.sh) decides whether a run has anything to test, and [cache-prune.yml](assets/cache-prune.yml) prunes a BuildKit `type=gha` cache.

## Verify

1. **`actionlint`** over every workflow. It catches schema and expression errors, and shellcheck findings in `run:` blocks.
2. **`zizmor .`** for template injection, unpinned actions, broad permissions and persisted credentials. Set `GH_TOKEN` for its online audits, which include checking that each pinned SHA belongs to the action it names. Without it, say the audit ran offline.
3. **A real run on a pull request.** Check that every job concluded as intended and read the step times. A workflow that parses but never ran is unverified.
4. **Prove each skip path.** Open a throwaway draft pull request whose only change is a file the skip should ignore. Check that the job reports skipped and the required check is green, then close it and delete its branch. In nvim-config#87 the docs-only draft (#88) showed `no test input changed: skip`, and its whole run took 10 s.
5. **Ask before `git push` or `gh workflow run`.** Both have effects outside the working copy. Name the branch and the workflow in the question.

Stop after three rounds of fixes that don't reduce the findings, and report what still fails, with its output. Silence a zizmor finding only in `zizmor.yml`, and give the reason there.

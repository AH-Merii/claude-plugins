# Required checks and skipping work

## Contents

- How a check gets its name
- What a skipped workflow or job reports
- Skip a job by changed files
- Aggregate split work into one check
- Rejected alternatives
- Merge queues

## How a check gets its name

- **A job's check is named by its `name:`, or by its id when there is no `name:`.** A ruleset or branch protection that requires `test` waits for that exact name.
- **A reusable workflow's jobs and matrix legs get their own names.** One run of a sharding experiment reported `b4-cache / suite 1/4` … `b4-cache / suite 4/4` and an aggregator `b4-cache / test` (`gh run view 39294838869 -R AH-Merii/nvim-config --json jobs`). Require the single fixed-name job, never a leg.
- **Workflows that aren't required can use path filters.** For example, a pruning workflow with `pull_request: paths: [.github/workflows/cache-prune.yml]` dry-runs only when it changes ([assets/cache-prune.yml](../assets/cache-prune.yml)).

## What a skipped workflow or job reports

From [GitHub: handling skipped but required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#handling-skipped-but-required-checks):

| Cause | Result |
| --- | --- |
| The workflow is skipped by `paths`/`paths-ignore`, a branch filter or a `[skip ci]` commit message | The check stays "Pending" and blocks the merge |
| The job is skipped by its `if:` | The job reports "Success" |
| A job it `needs` failed | The job is skipped and "may not block merging" |

The second row lets you skip work safely. The third is the trap: skipping a job you depend on can turn a failure into a green check.

## Skip a job by changed files

A `changes` job decides, and the required job reads its answer:

```yaml
jobs:
  changes:
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    permissions:
      contents: read
    outputs:
      tests: ${{ steps.inputs.outputs.tests }}
    steps:
      # Two commits: a pull request's merge commit and the base tip it was made on
      - uses: actions/checkout@<sha> # vX.Y.Z
        with:
          persist-credentials: false
          fetch-depth: 2
      - id: inputs
        run: bash .github/changed-inputs.sh "$EVENT" "$BEFORE"
        env:
          EVENT: ${{ github.event_name }}
          BEFORE: ${{ github.event.before }}

  test:
    name: test
    needs: changes
    # Skipped only on a clear "no": if `changes` fails, its output is empty and the tests run
    if: ${{ !cancelled() && needs.changes.outputs.tests != 'false' }}
```

That is nvim-config's `test.yml` from [#87](https://github.com/AH-Merii/nvim-config/pull/87). The script is [assets/changed-inputs.sh](../assets/changed-inputs.sh). The rules behind it ([D148](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#d148-ci-skips-what-it-doesnt-need-2026-10-19)):

- **List what is *not* an input, not what is.** Anything unlisted runs, so a new directory is tested until someone decides it can't affect the tests. Derive the list from what the build and tests actually read, such as the Docker build context, `.dockerignore`, the files tests open and the workflow files themselves. Then check it against history: replay recent merges through the script and confirm that release and docs-only merges skip and code merges run, as #87 did for main's last merges.
- **Diff what the run will test.** For a pull request that is the checked-out merge commit against its first parent, the base tip, so `fetch-depth: 2` is enough. For a push it is `HEAD` against `github.event.before`, which the script fetches when it is missing.
- **Any doubt runs.** That covers an unknown event, an all-zero `before` (a new branch), a base it can't fetch and a failed diff.
- **`!cancelled()` and `!= 'false'` together make it fail closed.** Without a status function, GitHub prepends `success()`, so a failed `changes` would skip `test`, and a skipped `test` is green. With `== 'true'`, the empty output of a failed `changes` would skip it too.

It pays off where many merges touch nothing the tests read. In nvim-config, 12 of the last 30 merged PRs were release PRs, which change only `CHANGELOG.md` and the release manifest, and each one ran the whole 6 to 9 minute job. A skipped run took 10 s (#87's PR description).

**Cost:** one more runner start and a shallow checkout ahead of the real job on every run (D148).

## Aggregate split work into one check

When a matrix or several jobs do the work, add one job named after the required check:

```yaml
  ci-ok:
    name: ci-ok
    if: always()
    needs: [validate, lint, test]
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - name: Require every check job to pass
        env:
          RESULTS: ${{ join(needs.*.result, ' ') }}
        run: |
          for result in $RESULTS; do
            [ "$result" = success ] || exit 1
          done
```

That is the `ci-ok` job in [AH-Merii/claude-plugins `.github/workflows/ci.yml`](https://github.com/AH-Merii/claude-plugins/blob/main/.github/workflows/ci.yml). Rules:

- **It runs when a dependency failed** (`always()` or `!cancelled()`). Otherwise it is skipped and reports success.
- **It reads every result.** Accept `skipped` only for jobs that skip on purpose, such as a test job gated by `changes`.
- **Keep one line per job in `needs:`.** A job left out of `needs:` isn't gated.

## Rejected alternatives

From D148 and GitHub's docs:

- **`paths:`/`paths-ignore:` on the workflow:** the required check stays pending on the pull requests it skips.
- **`dorny/paths-filter` or a similar action:** one more third-party action that holds the repository token, for a diff `git` does in a few lines.
- **An `if:` on every step of one job:** it needs no extra runner, but every new step has to remember the condition.
- **Skipping by branch name or author, e.g. release-please's branch:** a release PR that someone edits by hand would skip too.

## Merge queues

- **A merge queue needs its own trigger.** If a merge queue requires an Actions check, add `merge_group:` to the workflow's triggers, or the check is never reported for the queued merge (GitHub: [same page, merge queue section](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks#status-checks-with-github-actions-and-a-merge-queue)).
- **Teach the changed-files script about it.** Treat `merge_group` like any unknown event (run), or diff the queue's merge commit against its base the same way as a pull request.

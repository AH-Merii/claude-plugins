# Making CI faster

## Contents

- Measure first
- Drop what the runner doesn't need
- Don't run what nothing changed
- Cancel what nobody will read
- Shard a slow suite
- Slow and flaky tests

## Measure first

- **Per-step times, from several runs.** Use `gh run view <id> --json jobs`, with the jq in SKILL.md, over a handful of recent runs of the same workflow. In nvim-config the test job ranged from 413 to 585 s across 9 runs ([D148](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#d148-ci-skips-what-it-doesnt-need-2026-10-19)), so one before/after pair proves little. #87's own run took 7m40s and showed "no clear gain on a job that builds" ([#87](https://github.com/AH-Merii/nvim-config/pull/87)).
- **Read the logs for the step's premise,** not just its time: what it printed, how much it downloaded, what was cached. `gh run view <id> --log` prints the job name, step name and timestamp on every line.
- **Measure the verdict:** from the run's creation to the end of the job that decides pass or fail. Splitting work across jobs can shorten one step and lengthen the verdict ([nvim-config#86](https://github.com/AH-Merii/nvim-config/pull/86#issuecomment-6273802303)).
- **Report before and after with run IDs,** so the numbers can be checked.

## Drop what the runner doesn't need

- **Question each setup step against the log.** A "Free disk space" step deleted the runner's Android, .NET and GHC trees and took 47 to 119 s per run. The runner had 86 GB free (`/dev/root 145G 59G 86G 41%`, run 39290079036), not the ~14 GB its comment assumed. GitHub's runner table lists 14 GB of SSD for a 4-CPU Linux runner ([runner specs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)), so the free space was only visible in the log (D148).
- **Each extra action is also a dependency holding the token.** Fewer steps is a security gain too (security reference).

## Don't run what nothing changed

- **Skip the expensive job when no input changed,** with a job `if:` that fails closed, never with a trigger path filter on a required check. The pattern and its script are in [required-checks.md](required-checks.md).
- **Release PRs are the usual win.** release-please changes only the changelog and its manifest. In nvim-config that was 12 of the last 30 merged PRs, each running a 6 to 9 minute job. A skipped run took 10 s (#87).

## Cancel what nobody will read

- **Cancel superseded pull request runs** with `concurrency` and `cancel-in-progress`. Keep runs on the default branch that write caches or deploy uncancelled, e.g. `cancel-in-progress: ${{ github.event_name == 'pull_request' }}` (nvim-config `test.yml`, #87).

## Shard a slow suite

nvim-config#86 measured two ways to split a 215 to 247 s suite step, 3 runs each ([measurements](https://github.com/AH-Merii/nvim-config/pull/86#issuecomment-6273802303)):

| Way | N | Verdict (s) | Suite step (s) | Jobs |
| --- | --- | --- | --- | --- |
| One container (baseline) | 1 | 420 to 455 | 215 to 247 | 1 |
| N containers in one job | 4 | 289 to 307 | 76 to 91 | 1 |
| A matrix, each leg builds the image from the cache | 4 | 292 to 305 | 66 to 69 | 4 + aggregator |
| One build, legs `docker load` an artifact | 3 | 342 to 561, 2 of 3 failed | 89 to 92 | 1 + 3 + aggregator |

- **When setup is expensive, split inside one job first.** N processes or containers on one runner gave the same verdict as a 4-leg matrix, with one image build and no aggregator. Standard public-repo Linux runners have 4 CPUs (runner specs). At N=4 each check ran 1.08 to 1.32x slower than alone, against 0.87 to 1.08x on matrix legs, so keep N at or below the CPU count (nothing above N=4 was measured).
- **Don't share a large build output as an artifact to save rebuilds.** The 1 GB image tar took 21 to 29 s to upload. Each leg then spent 11 to 47 s downloading it and 33 to 42 s on `docker load`, all after the build job, which was slower than letting each leg build from the cache.
- **Balance shards longest-first from measured durations.** #86 kept per-check CI times in a file and assigned each check, longest first, to the currently lightest shard.
- **Prove the split covers everything.** Check that every test lands in exactly one shard, and that each shard's results file names what ran. A dropped shard must fail the check, not shrink it ("COVER PASS: 99 checks, each in exactly one of N shards", and it "failed as intended when the artifact build failed and no leg ran").
- **Keep fail-fast on** (the matrix default, [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstrategyfail-fast)), and give the aggregator the required check's name (see required-checks.md).
- **Check that order doesn't matter before splitting.** In #86 every check also passed alone in its own suite run (99 of 99), so no hidden order coupling was hit.

## Slow and flaky tests

- **Time each test from the suite's own output before rewriting any.** In nvim-config the four slowest checks spent 105 s of the suite's 235 s on CI (median of 5 runs) in fixed waits ([nvim-config#89](https://github.com/AH-Merii/nvim-config/pull/89)).
- **Wait for what settles the result, not a fixed time.** #89 replaced fourteen 3 s waits with "no lint running, the finding shown, the covering server's report in". The four checks went from 48.2, 20.7, 16.3 and 18.8 s to 7.6, 1.1, 1.0 and 12.3 s on CI. Together with sharding ([#90](https://github.com/AH-Merii/nvim-config/pull/90)), the test job took 5m07s (run 39302420252), against 413 to 585 s before.
- **"Nothing happens" needs a positive signal, not a timeout.** To prove that opening a file asks nothing, #89 added a small query that says whether any prompt is still queued or under way, and the test waits until none is: 20.7 s became 1.1 s.
- **Rewritten checks must still catch the bugs.** #89 ran each new check against sibling wrong versions of the code, one bug each. Two of the old timing-based checks had passed bugs the new ones catch: a re-lint case that never ran a lint, and a race in a reset case.
- **Cut per-call overhead in hot loops.** Calling the client binary directly instead of a wrapper script took 3 ms a call instead of 32 ms, over 146 calls (#89).
- **A fixed timeout also flakes.** One check failed with `Formatter 'tombi' timeout` both under 3-way contention and alone on its own runner, so load alone doesn't explain it (#86 measurements). Where a deadline remains, size it from measured headroom: under N=4 the tightest check used 21.6 s of its 40 s budget.
- **Keep the evidence of a failed run.** nvim-config's `test.yml` uploads the suite's output with `if: failure()` and `actions/upload-artifact`, so a flake's cause can be read after the runner is gone.

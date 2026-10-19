# Evals: shoop:writing-github-actions

They check whether the skill changes what an agent builds, by running the same tasks with and without
it and grading the result with deterministic checks. They live outside `plugins/` so they don't ship
with shoop.

## Scenarios

Each starts from a toy Python repo (`seed/base/`) plus the scenario's `overlay/`:

- **add-ci:** the repo has no CI. Add a workflow whose `test` check will be required, and skip the tests
  on docs-only pull requests.
- **fix-pending:** `paths-ignore` leaves the required `test` check pending on docs-only pull requests.
  Fix it, still without running the tests on them.
- **speed-up:** the job takes about 8 minutes. `ci-evidence/` holds the last run's step times and log
  excerpts, which show 86 GB free on a runner whose workflow frees disk space first.

The prompts are in `scenarios/*/prompt.md`. Fixture workflows are stored as `overlay/_github/` and
renamed to `.github/` when a trial's repo is seeded, so zizmor (`mise run check:workflows`) and GitHub
don't treat these deliberately flawed files as live workflows.

## Checks

`check.py <scenario> <repo> <seed>` prints `PASS` or `FAIL` for each check, and exits 0 only when all of them pass. A gate fails the run if the tests or the code under test changed. The checks:

- `valid`: actionlint accepts the workflows.
- `reports`: the required check runs on every PR: a non-matrix job named `test`, with no `paths:` or `paths-ignore:` on the `pull_request` trigger.
- `fail_closed`: `test` still runs when a job it needs fails. `check.py` evaluates its `if:` with that job failed.
- `skips_docs`: something keeps docs-only PRs from running pytest.
- Hardening (add-ci only): `pinned`, `least_privilege`, `timeouts`, `no_persisted_token`, `no_injection`, `concurrency`.
- Speed (speed-up only): `no_disk_cleanup`, `dep_cache`, `concurrency`.

`prove.py` shows that the checks bite. Every scenario must fail on its untouched repo and on 20 sibling
wrong workflows, each with one bug, built from `refs/ci.yml`. They must pass on the reference and on two
other correct designs (step-level `if:`s, and a matrix with an aggregator job). It prints `PROVE PASS`
when all of that holds.

## Running

You need `claude`, `uv`, `actionlint` and `zizmor` on `PATH`, e.g. through mise:

```sh
cd evals/writing-github-actions
mise exec actionlint@1.7.12 zizmor@1.30.1 -- uv run --no-project --with pyyaml python -I prove.py
mise exec actionlint@1.7.12 zizmor@1.30.1 -- ./run-round.sh r2 without with
```

`run-round.sh` copies the skill from `plugins/shoop/skills/writing-github-actions` into a stand-in plugin
named `gha-eval`, so it doesn't clash with an installed shoop. It then runs 3 samples of each scenario per
arm, 3 at a time, with `claude -p --model sonnet --effort low`, and prints a summary. Each trial is
capped at 2 GB under `systemd-run` where it exists. Outputs go to `$EVAL_OUT`, by default
`~/.cache/claude-plugins/evals/writing-github-actions/`: each trial's repo, the transcript
(`stream.jsonl`), `check.txt`, `diff.patch` and `tokens.json`. `tokens.py` sums usage over the
transcript's assistant messages, deduplicated by message id. `summarize.py <round dir>` reprints the
table.

Rerun the baseline arm in every round, and keep to one fix round before deciding.

## Results

Round 1, 2026-10-19, Claude Code 2.1.299, `claude-sonnet-5-5` at low effort, 3 samples per cell:

| Scenario | Arm | Pass | Median tokens | Cost, 3 runs | Failed checks |
| --- | --- | --- | --- | --- | --- |
| add-ci | with | 3/3 | 168,324 | $0.449 | none |
| add-ci | without | 0/3 | 86,353 | $0.300 | concurrency, fail_closed, no_persisted_token, pinned, timeouts |
| fix-pending | with | 3/3 | 171,324 | $0.448 | none |
| fix-pending | without | 3/3 | 85,818 | $0.287 | none |
| speed-up | with | 3/3 | 247,615 | $0.472 | none |
| speed-up | without | 0/3 | 154,242 | $0.344 | concurrency |

Every with-skill run loaded the skill on its own. The pinned SHAs in its runs matched the releases
resolved with `gh api` that day: checkout v7.0.1, setup-python v7.0.0. Without the skill, no run put
`paths:` on the required check, so on this model the skill's gain is the hardening and the fail-closed
`if:`.

## Isolation caveat

Both arms run with the local user's Claude Code setup: user rules, installed plugins and hooks.
Neither a temporary `HOME` nor `--setting-sources` removed them, and `--safe-mode` also drops
`--plugin-dir`. So the only difference between the arms is the skill, but the absolute numbers depend
on the machine's setup.

# Examples

These examples use a made-up project, `tally`, a small CLI with a result cache and an `export` command. Issue and PR numbers are placeholders.

## What it does, then the decision and what it leaves out

Title: `ci: run the unit tests on every PR`

```markdown
On every pull request, runs `python3 -m unittest discover -s tests` on Python 3.12. The tests stay on the standard library, so the project gains no dependencies.

- If test files exist but the runner discovers nothing, the job fails, so a broken test layout can't pass silently.
- One job, with read-only permissions, pinned actions, and per-PR concurrency that cancels superseded runs.

The whole suite runs on every PR, not just the tests for changed files, because it takes under 10 seconds and this removes change detection and its edge cases.

Deliberately left out: integration tests against the real export service, scheduled runs and coverage thresholds.

Closes #41
```

## No issue behind it: the problem first, then how it was checked and the known gaps

Title: `feat(export): refuse to overwrite an existing file`

```markdown
`tally export report.csv` silently overwrote `report.csv` if it existed, so a mistyped name could destroy an earlier export with no way back.

This makes `export` refuse when the target exists and name `--force` as the way to overwrite. The refusal comes before any work, so nothing is half-written. A `--force` flag was chosen over a confirmation prompt because `export` runs in scripts, where a prompt would hang.

Checked with the unit tests (`python3 -m unittest discover -s tests`) and by hand: exporting twice to the same name refused the second time and left the first file byte-identical. Symlinked targets are followed rather than refused; that's a known follow-up.
```

## Kept current: the opening line before and after the implementation landed

Before:

> Specifies the `export` command before it exists, so the tests define the behaviour and the implementation follows (#41, #42). Nothing is implemented yet: every new test currently fails on the missing module.

At merge:

> Adds the `export` command, which writes a report as CSV or JSON. It was written tests-first: the tests defined the behaviour, then the implementation followed (#41, #42).

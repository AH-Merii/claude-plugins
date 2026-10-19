# shoop

Five skills for shipping work. Each one loads by itself when the task calls for it, so an
agent writes tests, issues, commits, PR descriptions and CI workflows the same way every time.

- **writing-tests:** writing, reviewing and fixing tests. Test behaviour, not
  implementation; spend effort on edge cases and easy-to-miss paths, not exhaustive happy
  paths; make sure every test can fail (a do-nothing stub, wrong implementations with one
  bug each); test the rule a bug breaks, not just the one case; keep tests unchanged
  through refactors; and review tests for real gaps, with sourced findings.
- **writing-issues:** filing issues and keeping them accurate as work changes them. Plain
  titles, problem first, decisions recorded as comments (decision, why, what was
  rejected), corrections in new comments, and a note when a PR covers only part of an
  issue.
- **conventional-commits:** `type(scope): description (#N)` titles, a body that says what
  changed, why and any decision, with sources and how it was checked, and how to cut
  changes into commits.
- **writing-prs:** PR titles and descriptions. What it does and which issues it covers,
  how it was checked, decisions with their reasons, what's deliberately left out, and
  `Closes #N` for the issues it completes.
- **writing-github-actions:** setting up, fixing, speeding up and securing GitHub Actions
  CI. A baseline for every workflow (read-only token per job, SHA-pinned actions,
  concurrency, timeouts, no `${{ }}` in `run:`), required checks that report on every PR
  (a job `if:` that fails closed, never a `paths:` filter), measuring step times before
  optimising, caches and their limits, sharding, and a verify loop with actionlint, zizmor
  and a real run. Its security reference is adapted from
  [konstruktoid/agent-instructions-skills](https://github.com/konstruktoid/agent-instructions-skills)
  (Apache-2.0; the license is bundled with it).

The skills don't assume this repo or any particular tool. The writing skills' examples use
a made-up project; writing-github-actions cites the measured CI runs its rules came from.

## Install

```sh
claude plugin marketplace add AH-Merii/claude-plugins && claude plugin install shoop@ah-merii
```

The skills appear as `shoop:writing-tests`, `shoop:writing-issues`,
`shoop:conventional-commits`, `shoop:writing-prs` and `shoop:writing-github-actions`. Claude loads one when a task matches
its description; you can also call one directly, e.g. `/shoop:writing-tests`.

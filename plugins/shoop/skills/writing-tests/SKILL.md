---
name: writing-tests
description: How to write, review and fix automated tests that check behaviour rather than implementation. Covers what deserves a test, fakes versus one live check, do-nothing-stub and wrong-implementation checks, testing the rule rather than the instance, refactor-proof tests, shared behaviour across variants, tests-first and the bug-fix loop, and reviewing tests. Use when writing tests, adding a regression test for a bug, reviewing or critiquing a test suite, answering test-review findings, or deciding whether something needs a test at all.
---

# Writing tests

Tests are the spec. They say what the code must do, the default suite runs offline, and on merged code it passes. Start from the behaviour, not from the code's structure or the real tool it calls.

## What deserves a test

- **Test what's easy to miss.** Cover edge cases, error paths, refusals, and paths besides the happy one.
- **Be selective about happy paths.** Keep the few high-level ones that define the feature. Exhaustive happy-path coverage is padding.
- **Don't re-test libraries or tools.** Whether a dependency does what it says is implicit.
- **Plumbing needs no tests.** If a real run already exercises it (CI config, build tasks, wiring), that run's output is the evidence. Scale the method to the task.
- **Reminder-style code gets the obvious cases.** If the code only catches forgetfulness, such as a guard or a lint, test the obvious forgetful cases. Skip the rare or adversarial forms its purpose leaves out.

## Test behaviour, not fidelity

- **Fakes support only the cases under test.** A fake for an external tool or service handles what the tests need. It doesn't model the real thing, and the implementation uses only the subset the fake handles.
- **Don't grow fakes to match the real tool.** Prefer deleting weak or duplicate tests over expanding a fake.
- **Fake only at the outside boundary.** Use the real dependency when it's cheap and local, such as a real file system or VCS in a throwaway directory. Time and randomness count as outside boundaries: inject or fake them.
- **One opt-in live check against the real thing, when there is a real thing to check.** It is off by default behind an explicit switch, and it runs one realistic scenario end to end. It is the only check of fidelity.
- **Assert what callers can observe.** That means outputs, exit codes, files, and requests sent to the outside world. Don't assert internal calls. Counting outgoing requests is fine when the count is the behaviour, e.g. "one request per submission".
- **Check results through the interface when it has a read path.** Query storage directly only when the stored file, row or request is itself the contract.
- **Match the project's test runner and style.** A zero-dependency tool shouldn't gain test dependencies, so it uses the language's built-in runner.

## Every test must be able to fail

- **It fails against a do-nothing stub.** Replace the code under test with one that does nothing: returns nothing, returns empty, or exits successfully. Every test must then fail. A test that passes on silence checks nothing.
- **Expected values come from an independent source.** Use a literal, a worked example or the spec. Never recompute them the way the code does: the test then shares the code's bugs and passes with them.
- **Guard loops over derived lists.** If a test iterates over cases taken from the code, also assert that the list isn't empty or holds known members. Otherwise a stub gives zero iterations and the test passes.
- **Wrong-implementation checks prove a test bites.** For the rules that matter, write throwaway wrong implementations, each with **one** plausible bug. The suite must fail on each one.
  - **Variants are siblings, not stacked.** Each starts from the correct code and adds a single bug. That way each failure points to exactly one bug and one test.
  - **They are evidence, not part of the suite.** Keep them out of the reviewed diff and make them rerunnable against a given commit. Cite them in review as "this wrong implementation passes the suite".

## Test the rule, not the instance

- **Name the rule a case breaks.** Then check it across the variations that rule implies, using parameterised cases or subtests, not just the one case that was reproduced.
- **Variations stay inside the purpose.** Cover what the rule implies. Don't chase cases the purpose excludes.
- **Test shared behaviour as one rule over all variants.** Several commands, verbs or endpoints may share a behaviour such as auth, attachments or error format. Test it once over every variant, with the variant list derived from the code (e.g. the registered commands), so a new variant that misses it fails.
- **Add a completeness check.** It fails when a new variant isn't classified as having or lacking the shared behaviour.
- **Opt-in or copied shared behaviour is a design defect.** Extract it into one path that every variant inherits. Don't add a per-variant flag.

## Tests survive refactors

- **A refactor passes the existing tests unchanged.** A renamed call site is the only allowed edit. Inputs and expected outputs stay the same.
- **A test that had to change was checking the implementation.** If you edit a test beyond a call site during a refactor, report it so it gets reviewed.
- **Name tests for what they check, not how.** A name like "rejects an expired token" survives a rewrite; "calls validate twice" doesn't.

## Tests first

- **Tests define the behaviour, then the implementation follows.** If the work has an independent reviewer, the tests are reviewed against this skill before the implementation is written.
- **Batch when the behaviour is known, slice when it isn't.** For a bug fix or a specified feature, write and review the tests as one batch. When the interface is still unsettled, work one slice at a time: its tests, their review, its implementation, then the next. Bulk tests against an imagined interface check imagined behaviour.
- **Implement only what the tests require.** No speculative features or anticipated cases.
- **Tests never merge alone.** The implementation lands in the same change.
- **Bug-fix loop.** It's the same loop, re-entered from review:
  1. A confirmed bug, from code review, a live run or a manual check against the real system, gets a failing test that captures its **rule**. Write that test from the rule, not by converting the repro.
  2. Those tests get an independent review, if the work has a reviewer.
  3. Only then is the fix written.
  4. Rerun the suite, and the live check if there is one.
  5. Then a fresh code review, if the work has a reviewer.

## Reviewing tests

- **Start from the purpose.** Use the code's purpose, the recorded decisions and what's out of scope. Drop findings already answered by a decision.
- **Report behaviour gaps.** Examples: an implied rule nobody tests, a wrong implementation that passes, a test that passes against a do-nothing stub, a test tied to the implementation.
- **Flag padding.** That covers tests of implicit or library behaviour, duplicate tests, and exhaustive happy paths.
- **Report a fake-vs-real difference only when it matters.** It matters when it lets a wrong implementation pass or leaves a test checking nothing. Otherwise it's noise.
- **Every finding names a real failure and carries a source.** A source is a `path:line`, a command and its output (such as the wrong implementation that passes), or a link. Unsourced findings are dropped, not argued.

## Answering test-review findings

- **The author evaluates every finding.** For each one, fix it or push back with sources. Don't apply findings wholesale, and don't let an orchestrating agent do it for you.
- **Pushback is raised once.** The reviewer accepts it or keeps the finding with its reason. The same point isn't argued again; a disagreement that remains goes to a human.

See [references/examples.md](references/examples.md) for a stub check, sibling wrong implementations, and a shared-behaviour test with its completeness check.

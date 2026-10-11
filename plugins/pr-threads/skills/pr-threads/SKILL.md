---
name: pr-threads
description: Review a GitHub pull request, or act on a review of one, through the `pr-threads` command. Use it for every PR review comment, suggested change, verdict, reply, thread resolution and general issue or PR comment, instead of `gh pr comment`, `gh pr review`, `gh issue comment` or `gh api` writes. Typical asks are "review PR 12", "address the review comments", "reply to the thread", "accept the suggestion", "resolve what's fixed", "is the PR ready", and "comment on issue 7".
---

# pr-threads

`pr-threads [--pr N] <verb> ...` works on the current branch's PR unless `--pr` is given.
Code is always named by local `path:line` or `path:start-end`, as in your checkout.

In a GitButler workspace the checked-out branch is `gitbutler/workspace`, which has no PR,
so always pass `--pr N` there.

## Reviewer

1. Check out the PR branch at its pushed head. Comments are refused while the local
   branch is ahead, behind or diverged, or the file has uncommitted edits, and on lines
   outside the PR diff; the refusal says what to do and which lines are commentable.
2. Stage comments. Nothing is posted yet, and they survive across commands:
   - `pr-threads comment app.py:10 "Why change this?"`
   - `pr-threads suggest app.py:21-22 "Name these."` with the replacement lines on stdin
     (a heredoc) or in `--replacement TEXT`. They replace the whole range; `--delete`
     suggests deleting it.
3. `pr-threads submit changes "Summary."` or `pr-threads submit pass "Summary."` posts
   every staged comment as one review from the reviewer bot. If it fails, the staged
   comments are kept; fix the cause and submit again. If they went stale (the PR head
   moved) or GitHub rejects them, `pr-threads discard` drops them.
4. Next round, after the author pushes, read their replies with `pr-threads threads` and
   answer each thread as the bot:
   - `pr-threads verify T1 <sha> ["note"]`: the fix is in `<sha>`, a commit of the PR.
   - `pr-threads withdraw T1 "reason"`: the author's pushback holds.
   - `pr-threads dispute T1 "reason"`: the finding stands against the author's pushback.
   - `pr-threads reopen T1 "reason"`: the fix didn't work. The thread stays open, and
     isn't disputed: nobody pushed back.

`submit`, `verify`, `withdraw`, `dispute` and `reopen` only run as the bot. If they print an install
link, stop and give it to the user; never fall back to posting from their account.

## Author

1. `pr-threads threads` lists only open threads, each with its id, `path:line` and the
   conversation. `--json` gives the same as data. A thread marked outdated points at the
   lines as they were in the reviewed commit.
2. For each thread, fix the code, or `pr-threads accept T1` to apply its suggestion to the
   local file. Accept refuses if those lines changed since the review; then edit by hand.
3. Commit and push the fixes with the normal workflow.
4. `pr-threads reply T1 "Fixed in abc123."` on each thread, as the user, or push back
   with a reason.
5. `pr-threads resolve T1 T2 ...`, as the user, once the bot has verified or withdrawn
   each thread. It resolves all or none, and says why any thread can't be resolved yet.

`pr-threads post N "text"` leaves a general comment on issue or PR `N` from the user's
login, for notes that belong to no line.

## Status

`pr-threads status` (or `--json`) reads the handoff off the PR:

- `pending`: no approval or change request yet.
- `changes`: some reviewer's latest verdict requests changes.
- `approved`: approved, but threads are still open (the count is shown).
- `pass`: approved, no change request outstanding, no open threads.

It also names the threads the bot disputes (still open, so they block `pass`) and gives
the round: how many verdicts the bot has submitted.

## Images

`--attach FILE[#ALT]` on `comment`, `suggest`, `submit`, `reply` and `post` embeds a
screenshot or GIF, uploaded with the user's login. Always give alt text that states what
the image shows; readers see the alt text and open the image only when a claim depends on it.

# pr-threads

A `pr-threads` command, a skill and a guard hook that let agents review GitHub pull
requests as threads pinned to local `path:line`:

- **The reviewer** stages comments and suggested changes locally, then submits them as one
  review with a `pass` or `changes` verdict, posted by a reviewer bot (GitHub won't let you
  approve or request changes on your own PRs). Lines outside the PR diff, uncommitted
  edits, and a branch that's ahead of, behind or diverged from the pushed head are refused
  up front.
- **The bot** answers each thread with a verdict: `verify` (the fix is in a commit of the
  PR), `withdraw` (the author's pushback holds) or `dispute` (the finding stands), each with
  its reason. `resolve` then runs as you, only on threads whose last comment is the bot's
  verification or withdrawal, since GitHub won't let the app resolve threads without
  write access to the code.
- **The author** sees only open threads, replies as you, and applies a suggestion to the
  local file, so it goes through the normal commit path.
- **Either side** reads the handoff state with `status`: `pending`, `changes`, `approved`
  (with open threads), or `pass`, plus the threads the bot disputes and the round (how many
  reviews the bot has submitted).
- **The guard** denies raw `gh pr comment`, `gh pr review`, `gh issue comment` and `gh api`
  review and comment writes, and names the `pr-threads` verb to use instead.

## Verbs

```
pr-threads [--pr N] comment path:line[-end] BODY [--attach FILE[#ALT]]...
pr-threads [--pr N] suggest path:line[-end] BODY [--attach ...]   < replacement
pr-threads [--pr N] suggest path:line[-end] BODY --replacement TEXT | --delete
pr-threads [--pr N] submit pass|changes SUMMARY [--attach ...]    # as the bot
pr-threads [--pr N] discard                                       # drop staged comments
pr-threads [--pr N] verify THREAD SHA [NOTE]                      # as the bot
pr-threads [--pr N] withdraw|dispute THREAD REASON                # as the bot
pr-threads [--pr N] resolve THREAD...                             # as you, one request
pr-threads [--pr N] threads [--json]
pr-threads [--pr N] reply THREAD BODY [--attach ...]
pr-threads [--pr N] accept THREAD
pr-threads [--pr N] status [--json]
pr-threads post NUMBER BODY [--attach ...]                        # issue or PR conversation
```

Without `--pr`, the current branch's PR is used; where the branch has none (a GitButler
workspace is always on `gitbutler/workspace`), pass `--pr N`. Staged comments live in
`$XDG_STATE_HOME/pr-threads/` (default `~/.local/state`) until a submit succeeds, or
`discard` drops them. Once the PR head moves past them, `submit pass` is refused, since it
would approve commits nobody reviewed; `submit changes` still goes out on the staged head.

`suggest` takes the replacement on stdin or from `--replacement`, never both, and refuses
an empty one unless `--delete` asks for the deletion. `accept` follows the reviewed lines
through your local edits, refuses if those lines changed, and keeps the file's line
endings.

`verify` refuses unless SHA is in the history of the PR head on GitHub. `resolve` resolves
all of its threads or none, and names each one that fails and why: no verification from
the bot, someone (even the bot) commented after it, or the bot disputes it.

## Requirements

- `python3` (tested on 3.14) and [`gh`](https://cli.github.com) 2.99 or newer, logged in.
- `git`, plus `bash`, `jq`, `openssl` and `curl` for the bot's token command.
- The plugin's `bin/` is on the Bash tool's `PATH` while the plugin is enabled, so agents
  run `pr-threads` as a bare command.

## Setup: the reviewer bot

`submit`, `verify`, `withdraw` and `dispute` run as a GitHub App. Without it they print
the install link, exit non-zero and post nothing. Create the app once:

```sh
python3 plugins/pr-threads/scripts/reviewer-setup.py [--owner LOGIN] [--org] [--name APP]
```

It opens GitHub's "create app" page with a manifest filled in (private, `pull_requests:
write` only). The owner defaults to your `gh` login (or `REVIEWER_APP_OWNER`), the name to
`<owner>-claude-reviewer` (or `REVIEWER_APP_NAME`), and `--org` creates it under an
organisation. After you confirm, it saves `app.json` and `private-key.pem` to
`${CLAUDE_REVIEWER_DIR:-~/.config/claude-reviewer}`. Then install the app on each repo it
should review, from the link it prints. The app's `slug` in `app.json` is how
`resolve` and `status` recognise the bot's comments and reviews.

`bin/reviewer-token [owner/repo]` turns those into a one-hour token scoped to one repo. It
is the default token command; set `PR_THREADS_TOKEN_CMD` to use another.

## Attachments

`--attach FILE#alt text` embeds a screenshot or GIF. It's uploaded with your own `gh`
login, since the bot's token can't upload, even when the bot posts the comment. `post`
hands the file to `gh issue comment --attach`. The other verbs upload it the way gh's own
`--attach` does: one POST to `uploads.github.com/user-attachments/assets`. GitHub doesn't
document that endpoint, so it could change. It needs write access to the repo, and an
uploaded image can't be deleted. Set `PR_THREADS_UPLOAD_CMD` to a command that takes a
file path, uploads it with your login and prints the asset URL to use something else.

## Tests

```sh
python3 -m unittest discover -s plugins/pr-threads/tests
```

They need only Python and git: a stand-in `gh` records each request. One opt-in round
against real GitHub runs with `PR_THREADS_LIVE=1`. It needs your `gh` login, the bot
installed on `AH-Merii/test` (or `PR_THREADS_LIVE_REPO`), and network access.

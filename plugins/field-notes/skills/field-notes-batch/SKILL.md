---
name: field-notes-batch
description: Batch-generate many Field Notes drawings (a whole icon library, dozens to hundreds of items) as headless Claude sessions forked from one base session that has already read the field-notes skill, so every fork starts on a warm prompt cache. Use it when asked to batch-draw, convert a library or a list of icons, launch parallel drawing sessions, or redo rejected items of such a run.
---

# Field Notes batch

One **base** session loads the `field-notes` skill, looks at its examples and the inspiration
images, runs the tools once, then takes the run's shared prompt and replies `OK`. Every item is then
drawn by a **fork** of that base (`claude -p --resume <base> --fork-session`) with identical flags,
so each fork starts with the skill already read and reads that whole context (about 67k tokens in
the AWS icon run) from the prompt cache instead of paying for it again.

Everything sits next to this file, in `<skill-dir>`:

- `scripts/batch.sh`: `base`, `probe`, `item <key>`, `redo <key> <n> <notes-file>`.
- `scripts/governor.sh <queue-file>`: starts forks while RAM and the `MAX` limit allow.
- `scripts/contact_sheet.py`: puts newly finished items on one PNG for review.
- `templates/`: `batch.env.example`, `base-load.md`, `run-prompt.md`.

The scripts read their settings from `batch.env` in the **run folder** (the current directory, or
`$BATCH_DIR`) and write to its `logs/`. They need bash, `jq` and Python 3; the governor's RAM check
reads `/proc/meminfo`, so it is Linux only. Run them by absolute path from the run folder.

## Steps

### 1. Set up the run folder

Copy `templates/batch.env.example` to `<run>/batch.env` and fill it in: `GROUP` (sessions are
named `<GROUP> - <item name>`), `MODEL`, `WORK_DIR`, `CLAUDE_FLAGS`, `ITEM_MESSAGE`. Every
directory a fork reads or writes goes in `CLAUDE_FLAGS` as an absolute `--add-dir`, and the
field-notes plugin as `--plugin-dir`. Then write:

- `queue.txt`: one item key per line, in drawing order.
- `names.tsv` (optional): `key<TAB>item name`, for readable session names.
- `approved.txt`: empty at first; one key per approved item.

Done when every path in `batch.env` exists and `queue.txt` holds every key to draw.

### 2. Write the base-load prompt and the run prompt

Both are templates: `{{NAME}}` becomes the variable `NAME` from `batch.env` (or the environment),
and an unset one stops the script before anything is sent.

- `base-load.md` (start from `templates/base-load.md`) is the base's first turn. It loads
  `field-notes` with the Skill tool, passing the inspiration folder as the argument; reads
  SKILL.md and `references/kit.md`; opens every image in `examples/before-after/` and in the
  inspiration folder; runs the tools once (the skill's `press_2d.py` example and the run's own
  build on an item that is already finished); and replies with a short summary. It draws nothing.
  Anything each fork would otherwise do first belongs here, read once and cached for all.
- `run-prompt.md` (start from `templates/run-prompt.md`) is the shared task: the run's style rules
  on top of the skill, each tool command with absolute paths, the steps for one item, and the
  exact one-line reply (`<key>: OK|FLAG - <what changed> - <seed>`). It ends with "Reply with
  exactly `OK`"; the item arrives in the next message.

Done when both files read as complete instructions for a session that sees nothing else.

### 3. Create the base

```sh
cd <run> && <skill-dir>/scripts/batch.sh base
```

Turn 1 sends `base-load.md`; turn 2 resumes the same session with `run-prompt.md`. Both replies and
costs are printed, the rendered prompts and the JSON replies go to `logs/`, and the session id goes
to `base.id`. Done when turn 1's summary names the style rules and tools and turn 2 replied `OK`.
If either is wrong, fix the template and run `base` again (a new base; `base.id` is replaced).

### 4. Check the cache hit on the first fork

```sh
<skill-dir>/scripts/batch.sh probe
```

It forks the base with "Reply with exactly OK." (session `<GROUP> - cache probe`) and compares what
the fork read from cache with the base's context. Done when it prints `cache HIT`. On `cache MISS`,
find what differs between the base and the fork: model, `CLAUDE_FLAGS`, `WORK_DIR`, or a base whose
cache expired. Then draw one real item, `batch.sh item <key>`, and read its output files and its
reply before starting the governor.

### 5. Start the governor

```sh
<skill-dir>/scripts/governor.sh queue.txt
```

Run it in the background and let its exit wake you. It walks the queue and starts
`batch.sh item <key>` only while fewer than `MAX` of its forks run and more than `MIN_MB` of RAM is
available, `STAGGER` seconds apart (set them in `batch.env` or the environment; `POLL` is the RAM
recheck interval). Each fork claims its item with `logs/<key>.json`, so approved, claimed and
finished items are skipped, and a second governor on the same queue never draws an item twice.

- Drain: `touch logs/STOP`. No new forks start; running ones finish. Remove it before the next run.
- Stop everything: `kill $(cat logs/governor.pid)`. It stops its running forks too.

Done when the governor exits and `logs/results.log` has a line for every key in the queue.

### 6. Review in batches

```sh
python3 <skill-dir>/scripts/contact_sheet.py --image 'out/{prefix}-hand-drawn/check/{key}.png'
```

`--image` is the item's check image, relative to the run folder: `{key}` is the key, `{prefix}` its
part before the first `-`. It shows each finished item once (redos included, latest only), leaves
out approved items, writes `sheets/batch-NN.png` with each image labelled by its key, and prints
the path and the keys. Read the PNG and judge each item against the field-notes example set. Add
each good key to `approved.txt`; for each weak one, write a notes file saying what is wrong. Done
when every key on the sheet is approved or has notes.

### 7. Redo rejected items

```sh
<skill-dir>/scripts/batch.sh redo <key> <n> notes/<key>.md
```

A redo is a fresh fork of the base, named `<GROUP> - <item name> - redo<n>`, whose message is
`ITEM_MESSAGE` plus `REDO_MESSAGE` with the notes. It is always a fork of the base: the drawing
session that made the weak version would carry its mistakes forward and lose the warm cache. The
notes describe the problems in words, so the new fork judges the item fresh. Redos run even when
the key is approved. Review them on the next contact sheet.

## Logs

In `logs/`: `<tag>.json` and `<tag>.err` per fork (the tag is the key, or `<key>-redo<n>`),
`results.log` (each fork's last reply line), `costs.tsv` (`tag<TAB>cost in USD<TAB>session name`),
`shown.txt` (what the contact sheets showed), and the base's `base-load.json` and `base.json`.

## Gotchas

- **Identical flags, or no cache.** The forks hit the base's cache only with the same model, flags,
  `--add-dir`s, plugins and working directory as the base. `batch.sh` builds both from the same
  `batch.env`; change `CLAUDE_FLAGS` only before `batch.sh base`, then make a new base.
- **The cache lives one hour.** The JSON replies report `ephemeral_1h_input_tokens`: the cache TTL
  is 1 h, and each cache hit refreshes it
  ([prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)). A run that
  keeps forking stays warm; after an idle hour the next fork pays to write the cache once again.
- **The RAM check happens only at start, and forks grow afterwards.** Each fork used about
  240-340 MB, plus Chromium spikes during builds. Leave headroom: `MAX=24` and `MIN_MB=3500` worked
  on a 15 GB laptop.
- **Keep the stagger short.** A 15 s stagger starved the pool: forks finished faster than new ones
  started. The runner that replaced it used 3 s, the default.
- **The governor waits on its own children.** It replaced `xargs -P`, which stops launching once a
  child is killed by a signal. A fork killed by a signal ends only its own slot here.
- **Kill by pid.** A `pkill -f` pattern can match the shell running the command; use
  `logs/governor.pid` and the pids of the forks.
- **A failed fork keeps its claim.** Its `logs/<key>.json` holds the error and the item is skipped
  from then on. Delete that file to queue the item again.
- **The base stays as it is.** Every run touches it only through `--fork-session`; a plain
  `--resume` of the base would add turns to the context every later fork starts from.

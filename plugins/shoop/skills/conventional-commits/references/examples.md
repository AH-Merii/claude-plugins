# Examples

These examples use a made-up project, `tally`, a small CLI with a result cache and an `export` command. Issue numbers, paths and URLs are placeholders.

## Cause first, then the change, then how it was checked

```
refactor(cache): split load_entry under the complexity limit (#42)

load_entry was 14 against a limit of 10. Its two retry loops move into
wait_for_lock and read_payload, unchanged. Checked live: tally report
built, cached and reread a 50 MB input.
```

## A mechanical commit, standing alone

```
style: format the whole repo with the project formatter (#42)

Mechanical: formatter run with the line length from the shared config, so
the new lint check passes. No behaviour change.
```

## Several independent changes as bullets

```
fix: pass the type checker across the repo (#42)

- Narrow optional values before use (regex matches, a subprocess pipe).
- The HTTP handler's log method matches its base class's signature.
- The optional GUI import is ignored: a system library, absent in CI.
```

## Carrying out a recorded decision

```
feat(cache): key entries by content hash (#42)

Decision: https://github.com/example/tally/issues/42#issuecomment-1000001
Entries were keyed by modification time, which cp -p keeps, so an edited
input could be served a stale report. Each entry is now keyed by the
SHA-256 of the input's bytes, read in 1 MiB chunks.
```

## A tests-first pair: same rule, test first

```
test(cache): an edited input never gets a stale report

Rerunning after the input changes must rebuild the report, including when
the edit keeps the file's modification time (cp -p).
```

```
fix(cache): an edited input never gets a stale report (#42)

The cache matched entries by modification time, which cp -p preserves.
It now matches by content hash, so any edit misses the cache.
```

## A source and what prompted it

```
test(export): drop the fake writer's unused append mode

export now always writes a new file (src/export.py:31-33), so the fake's
append branch was dead. Raised in code review.
```

## No body needed

```
test(export): drop a duplicate CSV header test
```

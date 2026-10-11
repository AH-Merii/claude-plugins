# Examples

These examples use a made-up project, `tally`, a small CLI with a result cache and an `export` command. Issue numbers, SHAs, paths and URLs are placeholders. `[…]` marks text left out.

## A body: the problem, then what should be true

Title: `Cached results go stale after the source file changes`

```markdown
`tally` caches each report by input path. When the input file changes, the cache still returns the old report, so a user who edits their data and reruns sees yesterday's numbers with no warning. Two people reported wrong totals this way last week (#40, #44).

A rerun should always reflect the current input. A stale entry should never be served, and clearing the cache should stay possible by hand. The cache should still save time on unchanged inputs.

Related: #38 (cache size limits).
```

The proposed design and its open questions go in the first comment, headed "Implementation notes".

## A decision comment with several decisions, one heading each

```markdown
**Decision: how cache entries are invalidated** (branch `cache-invalidation`)

Measured on `main` at e4f5a6b. Every command below was run from the repo root.

### Key: content hash, not modification time
- **Decision:** key each entry by the SHA-256 of the input file's bytes.
- **Measured:** hashing a 50 MB input takes 0.08 s (`time tally hash big.csv`), against 4.1 s to build its report, so the hash costs about 2% of a miss.
- **Rejected:** modification time. `cp -p` and some sync tools preserve it, so a changed file can keep its old time and be served stale.

### Expiry: none by default
- **Decision:** entries don't expire; `tally cache clear` removes them by hand.
- **Why:** with a content key, an entry can't go stale, so a TTL would only cost rebuilds.
- **Rejected:** a 24-hour TTL, which rebuilds unchanged inputs daily for no gain.
```

## Sources pinned to a commit

```markdown
Decided, while implementing (a1b2c3d):

- **Hash in chunks.** The input is read in 1 MiB chunks ([`src/cache.py:40`](https://github.com/example/tally/blob/a1b2c3d/src/cache.py#L40-L46)), so memory stays flat for large files. Rejected: reading the whole file at once, which held a 2 GB input in memory during the test run.
```

## A known limit

```markdown
**Known limit, accepted after code review:**

- **The case:** an input is changed and changed back within the same second while `tally` is running.
- **What goes wrong:** the report built from the intermediate version can be cached under the final version's hash.
- **Why it isn't handled:** it needs two writes during one run; `tally` reads its input once, at start (`src/report.py:12`).
- **It can be fixed:** hash after building as well as before, and skip caching if they differ. A 5-line sketch passed the suite.
```

## Corrections and clarifications

- Clarifying the body: "Clarification: "clearing the cache should stay possible" in the body means the `tally cache clear` command, not deleting the cache folder by hand; see #38."
- Replacing an earlier decision: "Decided, replacing "entries expire after 24 hours" from the earlier comment: entries don't expire, because the content key already prevents stale results. […]"
- Correcting a mistake: "**Correction to the comment above.** `cp -p` preserves modification time on Linux and macOS alike (`man cp`), so the rejection holds on both. […]"

## Partly-done comment

"The CLI part landed in #57 (merged as e4f5a6b): `tally cache clear` and content-keyed entries. This issue stays open for the cache size limit."

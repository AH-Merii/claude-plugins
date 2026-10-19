# Caching

## Contents

- Limits and eviction
- Who can restore what
- Dependency caches
- Docker layer caches (BuildKit `type=gha`)
- Pruning a BuildKit cache
- Where not to cache

## Limits and eviction

From GitHub's [dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching):

- **10 GB per repository by default.** Past it, GitHub deletes caches by last access date until the total is under.
- **Entries unused for over 7 days are removed.**
- **An entry can't be changed.** A new content needs a new key, so key on a hash of what determines the content (`hashFiles('**/requirements*.txt')`), not on a date or run number.

Check the usage with `gh api repos/OWNER/REPO/actions/cache/usage` and list entries with `gh cache list`. One repository's cache stood at 10.29 GB in 232 entries, above the limit, and most of it was stale Docker layers ([nvim-config D149](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#d149-a-daily-job-prunes-the-build-cache-2026-10-19)).

## Who can restore what

From the same page:

- **A run can restore caches created on its own branch or on the default branch.** A pull request run can also restore its base branch's caches.
- **A pull request's own caches are scoped to its merge ref,** so only re-runs of that pull request can restore them.

So write caches from the default branch and let pull requests read them. nvim-config writes its image cache only on main (`cache-to: ${{ github.ref == 'refs/heads/main' && 'type=gha,mode=max' || '' }}`), because the `mode=max` write takes about 3 minutes and a pull request's copy would serve only its own re-runs ([test.yml](https://github.com/AH-Merii/nvim-config/blob/main/.github/workflows/test.yml)).

- **A pull request opened right after a merge races main's cache write.** The layers that main's build hasn't exported yet are missing from the cache, so the pull request rebuilds them. In nvim-config, release-please opened a release PR as soon as a feature merged. The PR's build (run 39286919053) started at 16:38:57 and ran the image's plugins stage uncached. Main's run 39286873140 finished exporting to the Actions cache only at 16:42:11 (`#39 exporting to GitHub Actions Cache … DONE 23.1s`). The release PR's build took 179 s for layers main was about to cache (`gh run view <id> --repo AH-Merii/nvim-config --json jobs` and `--log`).
- **Skipping the job avoids the race.** A release PR that changes no input never builds. nvim-config's changed-inputs skip ([D148](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#d148-ci-skips-what-it-doesnt-need-2026-10-19), see [required-checks.md](required-checks.md)) now spares its release PRs the build entirely.

## Dependency caches

- **Prefer the setup action's own cache** when there is one, e.g. `actions/setup-python` with `cache: pip`. It keys on a hash of `requirements.txt` or `pyproject.toml` by default. Set `cache-dependency-path` when the dependencies live in other files, such as `requirements-dev.txt` ([setup-python README](https://github.com/actions/setup-python#caching-packages-dependencies)).
- **Otherwise use `actions/cache`** with a key that includes the OS, the tool version and a lockfile hash, plus a `restore-keys` prefix for a partial hit.
- **Check that it hits.** "A cache key that never hits costs storage and time; one that is too loose restores stale content" ([konstruktoid, scalability](https://github.com/konstruktoid/agent-instructions-skills/blob/main/skills/github/github-actions-security/references/scalability.md)).

## Docker layer caches (BuildKit `type=gha`)

- **Use `mode=max` when the expensive layers are in an intermediate stage.** `mode=min` caches only the final stage's layers, so a tools stage would rebuild on every change ([nvim-config "Cache and CI"](https://github.com/AH-Merii/nvim-config/blob/main/docs/test-image-decisions.md#cache-and-ci-2026-10-17)).
- **`load: true` (`--load`) costs time even when every layer is cached.** It exports the image into the Docker daemon: `#37 exporting to docker image format … DONE 61.3s` in a build where every layer came from the cache (nvim-config run 39289495752). Each matrix leg that builds and loads the image pays it again.
- **Don't trust last access for BuildKit entries.** BuildKit stores one entry per layer blob (`buildkit-blob-1-<digest>`) and, per exporting build, an index (`index-buildkit-1-<scope>#<n>`) that lists the build's blobs. A build reads only the newest index, and it checks which blobs exist by listing keys, not reading them ([gha.go](https://github.com/moby/buildkit/blob/master/cache/remotecache/gha/gha.go), `initActiveKeyMap`). A fully cached build of main touched about 10 entries, so the layers in use can look older than stale ones, and GitHub's eviction can drop the layer that matters. Losing it there meant a cold build of 365 s (D149).

## Pruning a BuildKit cache

[assets/cache-prune.yml](../assets/cache-prune.yml) runs daily, on demand, and as a dry run on pull requests that change it. It keeps every blob the newest index lists, that index, and anything younger than 6 hours (a build uploads its blobs before its index), and deletes the other BuildKit entries. Its token has `actions: write` only.

- **It fails closed.** It deletes nothing while a build of the branch is queued or running, when it can't read the index, or when the index names no blob in the cache.
- **What it found:** the dry run read `index-buildkit-1-f921bd05#47: 30 layers, 30 of them in the cache` and would have deleted 161 of 232 entries (7.90 GB), keeping 71 (2.39 GB). The current tools-layer blobs were not on its delete list ([nvim-config#87](https://github.com/AH-Merii/nvim-config/pull/87)).
- **Known limit:** it reads the index through the runner's cache service, as BuildKit does ([cache_v2.go](https://github.com/tonistiigi/go-actions-cache/blob/master/cache_v2.go)). That isn't a documented API, so if it changes, the job fails before deleting anything (D149).
- **Rejected:** deleting by last access or age alone, which can delete the current layers. Keeping the newest entry per key, which keeps everything, since every blob key is unique. Raising the limit, which costs money and still fills (D149).

## Where not to cache

- **No caches in release or publishing workflows,** including setup actions' implicit caches. A job that runs in the default branch's context on untrusted input, such as `pull_request_target` or `workflow_run`, can write an entry that later default-branch runs restore. A poisoned entry restored into a release build reaches the published artifact (security reference).

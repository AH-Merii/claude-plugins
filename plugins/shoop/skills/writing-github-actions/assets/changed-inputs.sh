#!/usr/bin/env bash
# usage: changed-inputs.sh <event> [<before>]
# Copy into the repository (e.g. .github/changed-inputs.sh) and edit not_input() for it.
#
# Says whether a run has anything to test: prints the changed files and writes tests=true or
# tests=false to $GITHUB_OUTPUT (stdout when unset). tests=false only when every changed file is
# one the build and the tests never read. Anything else, a new path included, and any doubt (an
# unknown event, a base it can't fetch, a failed diff) prints tests=true. The job that runs the
# tests skips only on an explicit false:
#   if: ${{ !cancelled() && needs.changes.outputs.tests != 'false' }}
#
#   pull_request  the checked-out merge commit against its first parent, the base branch's tip
#                 (check out with fetch-depth: 2)
#   push          HEAD against <before> (github.event.before), the commit the push moved the
#                 branch from; fetched when the checkout doesn't have it
#
# From AH-Merii/nvim-config .github/test-inputs.sh (docs/test-image-decisions.md, D148).
set -uo pipefail
out=${GITHUB_OUTPUT:-/dev/stdout}
decide() {
  echo "tests=$1" >>"$out"
  echo "$2"
  exit 0
}

# Files the build and the tests never read. Exceptions (docs the tests do read) go first.
not_input() {
  case $1 in
    docs/generated-table.md) return 1 ;; # example: a doc a test renders and compares
    docs/* | .claude/* | .githooks/*) return 0 ;;
    CHANGELOG.md | .release-please-manifest.json | release-please-config.json) return 0 ;;
    README.md | CONTRIBUTING.md | AGENTS.md | CLAUDE.md | LICENSE | .gitignore) return 0 ;;
    *) return 1 ;;
  esac
}

case ${1:-} in
  pull_request) base=HEAD^1 ;;
  push)
    before=${2:-}
    [[ $before =~ ^[0-9a-f]{40}$ && ! $before =~ ^0+$ ]] || decide true "no previous commit to compare with: run"
    git cat-file -e "$before^{commit}" 2>/dev/null || git fetch -q --no-tags --depth=1 origin "$before" ||
      decide true "can't fetch $before: run"
    base=$before
    ;;
  *) decide true "event ${1:-none}: run" ;;
esac

files=$(git diff --name-only --no-renames "$base" HEAD) || decide true "git diff $base HEAD failed: run"
echo "changed files against $base:"
echo "${files:-(none)}"
while IFS= read -r f; do
  [ -z "$f" ] || not_input "$f" || decide true "$f is a test input: run"
done <<<"$files"
decide false "no test input changed: skip"

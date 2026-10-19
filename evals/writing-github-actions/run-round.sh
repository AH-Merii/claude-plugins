#!/usr/bin/env bash
# usage: run-round.sh <round> <arms...>   e.g. run-round.sh r2 without with
# Runs 3 samples of every scenario for each arm, at most 3 trials at once. Output goes to
# $EVAL_OUT (default: ~/.cache/claude-plugins/evals/writing-github-actions), never the repo.
set -uo pipefail
E=$(cd "$(dirname "$0")" && pwd)
export EVAL_OUT=${EVAL_OUT:-${XDG_CACHE_HOME:-$HOME/.cache}/claude-plugins/evals/writing-github-actions}
round=$1
shift
for tool in claude uv actionlint zizmor; do
  command -v "$tool" >/dev/null || {
    echo "$tool isn't on PATH (see README.md)" >&2
    exit 1
  }
done

# The with-skill arm loads a copy of the skill as its own plugin, so it doesn't clash with
# an installed shoop.
skill=$E/../../plugins/shoop/skills/writing-github-actions
rm -rf "$EVAL_OUT/plugin"
mkdir -p "$EVAL_OUT/plugin/.claude-plugin" "$EVAL_OUT/plugin/skills" "$EVAL_OUT/$round"
echo '{"name":"gha-eval","version":"0.0.0","description":"eval copy of shoop:writing-github-actions"}' \
  >"$EVAL_OUT/plugin/.claude-plugin/plugin.json"
cp -r "$skill" "$EVAL_OUT/plugin/skills/"

for arm in "$@"; do
  for scenario in add-ci fix-pending speed-up; do
    for sample in 1 2 3; do
      echo "$round $arm $scenario $sample"
    done
  done
done | xargs -P 3 -L 1 bash "$E/run-trial.sh" | tee -a "$EVAL_OUT/$round.log"
python3 -I "$E/summarize.py" "$EVAL_OUT/$round"

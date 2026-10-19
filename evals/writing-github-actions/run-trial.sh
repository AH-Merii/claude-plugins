#!/usr/bin/env bash
# usage: run-trial.sh <round> <arm: with|without> <scenario> <sample>
# Seeds a fresh repo for the scenario, runs Claude (Sonnet, low effort) on its prompt, then
# runs the outcome checks. Output lands in $EVAL_OUT/<round>/<arm>-<scenario>-<sample>/.
# run-round.sh sets EVAL_OUT and builds the with-skill plugin copy; see README.md.
set -uo pipefail
E=$(cd "$(dirname "$0")" && pwd)
: "${EVAL_OUT:?set EVAL_OUT (run-round.sh does)}"
round=$1 arm=$2 scenario=$3 sample=$4
out=$EVAL_OUT/$round/$arm-$scenario-$sample
rm -rf "$out"
mkdir -p "$out"
repo=$out/repo seed=$out/seed

cp -r --reflink=auto "$E/seed/base" "$repo"
cp -r --reflink=auto "$E/scenarios/$scenario/overlay/." "$repo/"
# Fixture workflows are stored as _github/ so zizmor and GitHub never treat them as live.
[ ! -d "$repo/_github" ] || mv "$repo/_github" "$repo/.github"
cp -r --reflink=auto "$repo" "$seed"
git -C "$repo" init -q -b main
git -C "$repo" add -A
git -C "$repo" -c user.name=eval -c user.email=eval@example.invalid commit -q -m "initial"

args=()
if [ "$arm" = with ]; then
  args+=(--plugin-dir "$EVAL_OUT/plugin")
fi

export TMPDIR=$out/tmp
mkdir -p "$TMPDIR"

# Cap each trial's memory where systemd is available.
cap=()
if command -v systemd-run >/dev/null; then
  cap=(systemd-run --user --scope -q -p MemoryMax=2G -p MemorySwapMax=512M --)
fi

start=$(date +%s)
(cd "$repo" && timeout 1200 "${cap[@]}" \
  claude -p --model sonnet --effort low --permission-mode auto --permission-prompts none \
  --no-session-persistence --output-format stream-json --verbose "${args[@]}" \
  "$(cat "$E/scenarios/$scenario/prompt.md")" >"$out/stream.jsonl" 2>"$out/stderr.log")
echo "claude_exit=$? seconds=$(($(date +%s) - start))" >"$out/meta.txt"

uv run -q --no-project --with pyyaml python -I "$E/check.py" "$scenario" "$repo" "$seed" >"$out/check.txt" 2>&1
git -C "$repo" add -A >/dev/null 2>&1
git -C "$repo" diff --cached >"$out/diff.patch"
python3 -I "$E/tokens.py" "$out/stream.jsonl" >"$out/tokens.json"
echo "$round $arm $scenario $sample $(tail -1 "$out/check.txt")"

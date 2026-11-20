#!/usr/bin/env bash
# Batch runner: one base session that has read the drawing skill, and one fork of it per item.
#
#   batch.sh base                        create "<GROUP> - BASE SESSION"; its id goes to base.id
#   batch.sh probe                       fork the base once with a one-word task and check the cache hit
#   batch.sh item <key>                  claim <key> and draw it in a fresh fork of the base
#   batch.sh redo <key> <n> <notes-file> a fresh fork of the base (never of the drawing session),
#                                        named "... - redo<n>", carrying the written notes
#
# Run it from the run folder (or set BATCH_DIR); settings come from its batch.env (see
# templates/batch.env.example). Results and costs go to logs/.
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
# shellcheck source=config.sh
source "$HERE/config.sh"

# Identical flags for the base and every fork: the forks hit the base's prompt cache only when the
# model, tools, directories and plugins match byte for byte.
COMMON=(--model "$MODEL" "${CLAUDE_FLAGS[@]}" --output-format json)

# render text TEMPLATE | render file PATH: replace each {{NAME}} with the environment variable NAME.
# An unset NAME is an error, so a typo never reaches a session.
render() {
  python3 -c '
import os, re, sys
mode, arg = sys.argv[1:]
text = open(arg).read() if mode == "file" else arg
def sub(m):
    if m.group(1) not in os.environ:
        sys.exit(f"batch.sh: template uses {{{{{m.group(1)}}}}}, which is not set")
    return os.environ[m.group(1)]
sys.stdout.write(re.sub(r"\{\{(\w+)\}\}", sub, text))' "$1" "$2"
}

# run_claude OUT ERR ARGS...: run claude in WORK_DIR; a TERM or INT to this script stops it too.
run_claude() {
  local out=$1 err=$2 pid
  shift 2
  # <&0: a background job's stdin is /dev/null unless redirected, and the base reads its prompt there.
  (cd "$WORK_DIR" && exec claude "$@") <&0 >|"$out" 2>"$err" &
  pid=$!
  trap 'kill "$pid" 2>/dev/null' TERM INT
  wait "$pid" || true
  trap - TERM INT
}

# record TAG NAME: append the reply's last line and the cost to the run logs.
record() {
  local line cost
  line="$(jq -r .result "$LOGS/$1.json" 2>/dev/null | tail -1)" || line=""
  cost="$(jq -r .total_cost_usd "$LOGS/$1.json" 2>/dev/null)" || cost=""
  [ -n "$line" ] || line="$1: no result (see $LOGS/$1.err)"
  echo "$line" >>"$LOGS/results.log"
  printf '%s\t%s\t%s\n' "$1" "$cost" "$2" >>"$LOGS/costs.tsv"
  echo "$line"
}

display_name() {
  local name=""
  [ -f "$NAMES" ] && name="$(awk -F'\t' -v k="$1" '$1==k{print $2; exit}' "$NAMES")"
  echo "$GROUP - ${name:-$1}"
}

base_id() {
  [ -s "$BASE_ID" ] || { echo "no base session yet: run batch.sh base first" >&2; exit 2; }
  cat "$BASE_ID"
}

case "${1:-}" in
  base)
    name="$GROUP - BASE SESSION"
    # Turn 1: load the skill, look at the examples, run the tools once. Turn 2: the run prompt, reply OK.
    render file "$BASE_LOAD" >"$LOGS/base-load.md"
    render file "$RUN_PROMPT" >"$LOGS/run-prompt.md"
    run_claude "$LOGS/base-load.json" "$LOGS/base-load.err" -p -n "$name" "${COMMON[@]}" <"$LOGS/base-load.md"
    id="$(jq -r .session_id "$LOGS/base-load.json")"
    jq -r '.result, "cost: \(.total_cost_usd)"' "$LOGS/base-load.json"
    run_claude "$LOGS/base.json" "$LOGS/base.err" -p --resume "$id" -n "$name" "${COMMON[@]}" <"$LOGS/run-prompt.md"
    jq -r .session_id "$LOGS/base.json" >"$BASE_ID"
    jq -r '.result, "cost: \(.total_cost_usd)"' "$LOGS/base.json"
    echo "base session: $(cat "$BASE_ID")"
    ;;
  probe)
    id="$(base_id)"
    run_claude "$LOGS/probe.json" "$LOGS/probe.err" -p --resume "$id" --fork-session \
      -n "$GROUP - cache probe" "${COMMON[@]}" "Reply with exactly OK."
    # The base's context at its last turn, against what the fork read from cache on its first call.
    context="$(jq '.usage | .input_tokens + .cache_read_input_tokens + .cache_creation_input_tokens' "$LOGS/base.json")"
    read_="$(jq '.usage.cache_read_input_tokens' "$LOGS/probe.json")"
    written="$(jq '.usage.cache_creation_input_tokens' "$LOGS/probe.json")"
    ttl="$(jq -r 'if (.usage.cache_creation.ephemeral_1h_input_tokens // 0) > 0 then "1h" else "5m or unknown" end' "$LOGS/probe.json")"
    echo "base context: $context tokens; fork read $read_ from cache, wrote $written; cache TTL: $ttl"
    if [ "$read_" -ge $((context * 8 / 10)) ]; then echo "cache HIT"; else echo "cache MISS: compare the flags and WORK_DIR of base and fork" >&2; exit 1; fi
    ;;
  item | redo)
    key="${2:?usage: batch.sh $1 <key>}"
    id="$(base_id)"
    name="$(display_name "$key")"
    tag="$key"
    if [ "$1" = item ]; then
      # Approved items are never redrawn, except as an explicit redo.
      if grep -qxF -- "$key" "$APPROVED" 2>/dev/null; then echo "skip approved $key"; exit 0; fi
      msg="$(KEY="$key" NAME="$name" render text "$ITEM_MESSAGE")"
      # Claim the item atomically: a log file that already exists means another runner has it.
      ( set -o noclobber; : >"$LOGS/$key.json" ) 2>/dev/null || { echo "skip claimed $key"; exit 0; }
    else
      n="${3:?usage: batch.sh redo <key> <n> <notes-file>}"
      notes="${4:?usage: batch.sh redo <key> <n> <notes-file>}"
      name="$name - redo$n"
      tag="$key-redo$n"
      msg="$(KEY="$key" NAME="$name" render text "$ITEM_MESSAGE")

$(KEY="$key" NAME="$name" FEEDBACK="$(cat "$notes")" render text "$REDO_MESSAGE")"
    fi
    run_claude "$LOGS/$tag.json" "$LOGS/$tag.err" -p --resume "$id" --fork-session -n "$name" "${COMMON[@]}" "$msg"
    record "$tag" "$name"
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac

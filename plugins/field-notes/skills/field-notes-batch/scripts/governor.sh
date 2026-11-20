#!/usr/bin/env bash
# Self-adjusting runner: walks a queue file (one key per line) and starts `batch.sh item <key>`
# only while fewer than MAX of its forks run and more than MIN_MB of RAM is available, STAGGER
# seconds apart.
#
#   governor.sh <queue-file>
#
# MAX, MIN_MB, STAGGER and POLL come from the environment or batch.env. To drain, `touch logs/STOP`:
# no new forks start and the running ones finish. To stop everything, `kill $(cat logs/governor.pid)`.
set -uo pipefail
HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
queue="$(realpath "${1:?usage: governor.sh <queue-file>}")"
# shellcheck source=config.sh
source "$HERE/config.sh"
MAX="${MAX:-4}"
MIN_MB="${MIN_MB:-3500}"
STAGGER="${STAGGER:-3}"
POLL="${POLL:-5}"
MEMINFO="${MEMINFO:-/proc/meminfo}"

# RAM available now, in MB. Without /proc/meminfo (not Linux) the RAM check is skipped.
available_mb() {
  if [ -r "$MEMINFO" ]; then
    awk '/^MemAvailable:/ {print int($2 / 1024); exit}' "$MEMINFO"
  else
    echo 999999999
  fi
}
[ -r "$MEMINFO" ] || echo "governor: no $MEMINFO, so only MAX limits the forks" >&2

finished() {
  grep -qxF -- "$1" "$APPROVED" 2>/dev/null || [ -e "$LOGS/$1.json" ]
}

# Our own children are counted by pid, never by a pgrep/pkill pattern, which can match the shell
# that runs this script.
trap 'kill $(jobs -p) 2>/dev/null; wait; exit 130' INT TERM
echo $$ >"$LOGS/governor.pid"
mapfile -t keys < <(sed -e 's/[[:space:]].*//' -e '/^#/d' -e '/^$/d' "$queue")
for key in "${keys[@]}"; do
  finished "$key" && continue
  while :; do
    [ -e "$LOGS/STOP" ] && break 2
    if [ "$(jobs -rp | wc -l)" -ge "$MAX" ]; then
      wait -n # a child that dies from a signal only ends its own wait; the loop goes on
      continue
    fi
    [ "$(available_mb)" -gt "$MIN_MB" ] && break
    sleep "$POLL"
  done
  finished "$key" && continue
  "$HERE/batch.sh" item "$key" </dev/null &
  sleep "$STAGGER"
done
wait
rm -f "$LOGS/governor.pid"

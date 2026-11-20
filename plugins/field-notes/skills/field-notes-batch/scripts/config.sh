# shellcheck shell=bash
# Sourced by batch.sh and governor.sh: loads the run folder's batch.env and fills in defaults.
# The run folder is $BATCH_DIR, else the current directory.
BATCH_DIR="$(cd "${BATCH_DIR:-$PWD}" && pwd)"
[ -f "$BATCH_DIR/batch.env" ] || { echo "no batch.env in $BATCH_DIR (copy templates/batch.env.example)" >&2; exit 2; }
cd "$BATCH_DIR" || exit 2
# Every plain variable in batch.env is exported, so the prompt templates can use it as {{NAME}}.
set -a
# shellcheck source=/dev/null
source "$BATCH_DIR/batch.env"
set +a
: "${MODEL:?set MODEL in batch.env}"
: "${GROUP:?set GROUP in batch.env (session names are \"<GROUP> - <item>\")}"
WORK_DIR="${WORK_DIR:-$BATCH_DIR}"
BASE_LOAD="${BASE_LOAD:-$BATCH_DIR/base-load.md}"
RUN_PROMPT="${RUN_PROMPT:-$BATCH_DIR/run-prompt.md}"
[ -n "${ITEM_MESSAGE:-}" ] || ITEM_MESSAGE='Your item: {{KEY}}'
[ -n "${REDO_MESSAGE:-}" ] || REDO_MESSAGE='A previous attempt at this item was rejected. Fix these problems:
{{FEEDBACK}}'
NAMES="${NAMES:-$BATCH_DIR/names.tsv}"
APPROVED="${APPROVED:-$BATCH_DIR/approved.txt}"
LOGS="${LOGS:-$BATCH_DIR/logs}"
BASE_ID="${BASE_ID:-$BATCH_DIR/base.id}"
# Relative paths in batch.env are relative to the run folder.
for v in WORK_DIR BASE_LOAD RUN_PROMPT NAMES APPROVED LOGS BASE_ID; do printf -v "$v" '%s' "$(realpath -m "${!v}")"; done
export BATCH_DIR WORK_DIR GROUP MODEL
[ "$(declare -p CLAUDE_FLAGS 2>/dev/null | cut -c1-10)" = "declare -a" ] || CLAUDE_FLAGS=()
mkdir -p "$LOGS"

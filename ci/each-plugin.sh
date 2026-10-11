# Sourced by the check tasks in mise-tasks/check/. Runs one check per plugin, keeps
# going after a failure, and names every plugin that failed, so a defect in one
# plugin fails that plugin's run and the others are still checked.
#
#   each_plugin <check-function> [dir...]
#
# With no dirs it checks every folder under plugins/. The check function gets one
# dir and returns non-zero when that plugin breaks the rule.

plugin_dirs() {
  find plugins -mindepth 1 -maxdepth 1 -type d -print0 | sort -z
}

each_plugin() {
  local check=$1
  shift
  local -a dirs failed=()
  if [ $# -gt 0 ]; then
    dirs=("$@")
  else
    mapfile -d '' -t dirs < <(plugin_dirs)
  fi
  local dir
  for dir in "${dirs[@]}"; do
    echo "::group::${MISE_TASK_NAME:-check} $dir"
    # </dev/null: a check must never read the caller's stdin.
    "$check" "$dir" </dev/null || failed+=("$dir")
    echo "::endgroup::"
  done
  for dir in "${failed[@]}"; do
    echo "::error::${MISE_TASK_NAME:-check} failed for $dir"
  done
  [ ${#failed[@]} -eq 0 ]
}

# True when the plugin has Python files outside caches.
has_python() {
  [ -n "$(find "$1" -name '*.py' -not -path '*/__pycache__/*' -print -quit)" ]
}

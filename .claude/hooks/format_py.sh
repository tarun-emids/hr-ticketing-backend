#!/bin/sh
# PostToolUse hook (WSL/Linux): auto-format + auto-fix the .py file Claude just
# wrote/edited. Reads the hook payload from stdin; no-ops when the file isn't
# under this repo or ruff isn't available. Config: pyproject.toml.
set -u
payload=$(cat)
[ -n "$payload" ] || exit 0
f=$(printf '%s' "$payload" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(1)
print((d.get("tool_input") or {}).get("file_path") or "")' 2>/dev/null) || exit 0
[ -n "$f" ] || exit 0
case "$f" in *.py) ;; *) exit 0 ;; esac
[ -f "$f" ] || exit 0
script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH='' cd -- "$script_dir/../.." && pwd)
case "$f" in "$repo_root"/*) ;; *) exit 0 ;; esac
if [ -x "$repo_root/.venv/bin/ruff" ]; then
    ruff="$repo_root/.venv/bin/ruff"
elif command -v ruff >/dev/null 2>&1; then
    ruff=ruff
else
    exit 0    # ruff not installed -> quiet no-op
fi
"$ruff" format -- "$f"; fmt=$?
out=$("$ruff" check --fix -- "$f" 2>&1); chk=$?
if [ "$fmt" -ne 0 ] || [ "$chk" -ne 0 ]; then
    printf '%s\n' "$out" >&2
    exit 2    # remaining findings: sent back to the model to fix
fi
exit 0

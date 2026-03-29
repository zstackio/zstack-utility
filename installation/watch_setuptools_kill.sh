#!/usr/bin/env bash
# Loop: read setuptools version (pip list, same idea as: pip list | grep setup).
# When it changes from the previous sample, send SIGTERM to TARGET_PID.

set -euo pipefail

TARGET_PID="${TARGET_PID:-226226}"
INTERVAL_SEC="${INTERVAL_SEC:-5}"
SIGNAL="${SIGNAL:-TERM}"

get_setuptools_version() {
  local line ver
  # pip 6.x style: "setuptools (21.0.0)"
  line=$(pip list 2>/dev/null | grep -i setuptools | head -1 || true)
  # Avoid [[ =~ ... ]] with captures: old bash/RHEL6–7 can throw "unexpected )".
  if [[ -n "$line" ]]; then
    ver=$(printf '%s\n' "$line" | sed -n 's/.*(\([0-9][0-9.]*\)).*/\1/p')
    if [[ -n "$ver" ]]; then
      echo "$ver"
      return 0
    fi
  fi
  # Column style: "setuptools  21.0.0"
  ver=$(pip list 2>/dev/null | awk 'tolower($1) == "setuptools" { print $2; exit }')
  if [[ -n "$ver" ]]; then
    echo "$ver"
    return 0
  fi
  # Same interpreter setuptools actually uses
  python -c 'import setuptools; print(setuptools.__version__)' 2>/dev/null || true
}

prev=$(get_setuptools_version)
if [[ -z "$prev" ]]; then
  echo "Could not read setuptools version (activate venv / check pip)." >&2
  exit 1
fi

echo "Watching setuptools (every ${INTERVAL_SEC}s, PID ${TARGET_PID}, signal ${SIGNAL}). Baseline: ${prev}"
echo "Stop with Ctrl+C."

while sleep "$INTERVAL_SEC"; do
  cur=$(get_setuptools_version)
  if [[ -z "$cur" ]]; then
    echo "$(date -Is) warn: empty version, skip" >&2
    continue
  fi
  if [[ "$cur" != "$prev" ]]; then
    echo "$(date -Is) setuptools changed: ${prev} -> ${cur}"
    if kill -"${SIGNAL}" "$TARGET_PID" 2>/dev/null; then
      echo "$(date -Is) sent SIG${SIGNAL} to ${TARGET_PID}"
    else
      echo "$(date -Is) kill ${TARGET_PID} failed (no such process or no permission?)" >&2
    fi
    prev="$cur"
  fi
done

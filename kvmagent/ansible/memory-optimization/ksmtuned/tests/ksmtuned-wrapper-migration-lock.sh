#!/bin/bash
# A legacy-config migration must not overwrite a newer Agent publication while
# waiting for the shared writer lock.
set -euo pipefail

root=$(mktemp -d)
trap 'kill "${runner:-}" 2>/dev/null || true; kill "${holder:-}" 2>/dev/null || true; rm -rf "$root"' EXIT
mkdir -p "$root/ksm" "$root/run"
printf '0\n' > "$root/ksm/run"
printf '0\n' > "$root/ksm/pages_to_scan"
printf '20\n' > "$root/ksm/sleep_millisecs"
printf '0\n' > "$root/ksm/use_zero_pages"
printf 'MemTotal: 67108864 kB\n' > "$root/meminfo"
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=1
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=0
EOF
lock="$root/run/lock"
touch "$root/run/marker"
flock "$lock" -c 'sleep 0.4' & holder=$!
wrapper="$(cd "$(dirname "$0")/.." && pwd)/ksmtuned-zstack"
KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$root/ksm" \
  KSMTUNED_MEMINFO="$root/meminfo" KSMTUNED_LOCK="$lock" \
  KSMTUNED_MARKER="$root/run/marker" KSMTUNED_SNAPSHOT="$root/run/snapshot" \
  "$wrapper" stop >/dev/null 2>&1 & runner=$!
sleep 0.1
# Simulate Agent's lock-protected atomic publication while migration is queued.
cat > "$root/conf.new" <<'EOF'
CONFIG_REVISION=9
KSM_ENABLED=1
KSM_PAGES_TO_SCAN=321
KSM_SLEEP_MILLISECS=30
KSM_ZERO_PAGES=1
EOF
mv "$root/conf.new" "$root/conf"
wait "$holder"
wait "$runner"
grep -q '^CONFIG_REVISION=9$' "$root/conf"
grep -q '^KSM_ENABLED=1$' "$root/conf"
grep -q '^KSM_PAGES_TO_SCAN=321$' "$root/conf"

#!/bin/bash
# The apply command must not publish its receipt before a delayed engine has
# written the requested sysfs values.
set -euo pipefail

root=$(mktemp -d)
runner=''
cleanup() { kill "${runner:-}" 2>/dev/null || true; rm -rf "$root"; }
trap cleanup EXIT
mkdir -p "$root/ksm" "$root/run"
printf 'MemTotal:       67108864 kB\n' > "$root/meminfo"
printf '0\n' > "$root/ksm/run"
printf '0\n' > "$root/ksm/pages_to_scan"
printf '0\n' > "$root/ksm/sleep_millisecs"
printf '0\n' > "$root/ksm/use_zero_pages"
printf '0\n' > "$root/ksm/merge_across_nodes"
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=7
KSM_ENABLED=1
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
cat > "$root/engine" <<'EOF'
#!/bin/sh
trap ':' USR1
(
  trap '' USR1
  sleep 1
  echo 2000 > "$KSMTUNED_KSM_ROOT/pages_to_scan"
  echo 20 > "$KSMTUNED_KSM_ROOT/sleep_millisecs"
  echo 1 > "$KSMTUNED_KSM_ROOT/run"
  echo 1 > "$KSMTUNED_KSM_ROOT/use_zero_pages"
  while :; do sleep 1; done
) &
echo $! > "${KSMTUNED_PIDFILE:?}"
exit 0
EOF
chmod +x "$root/engine"
wrapper="$(cd "$(dirname "$0")/.." && pwd)/ksmtuned-zstack"
KSMTUNED_ENGINE="$root/engine" KSMTUNED_CONF="$root/conf" \
KSMTUNED_KSM_ROOT="$root/ksm" KSMTUNED_LOCK="$root/run/lock" KSMTUNED_SNAPSHOT="$root/run/snapshot" \
KSMTUNED_MARKER="$root/run/marker" KSMTUNED_APPLIED="$root/run/applied" \
KSMTUNED_RUNTIME_DIR="$root/run" KSMTUNED_PIDFILE="$root/run/engine.pid" \
KSMTUNED_MEMINFO="$root/meminfo" "$wrapper" apply >"$root/out" 2>&1 &
runner=$!
sleep 0.2
test ! -e "$root/run/applied" || { echo 'receipt published before delayed engine applied' >&2; exit 1; }
deadline=$(( $(date +%s) + 5 ))
while [ ! -e "$root/run/applied" ]; do
    [ "$(date +%s)" -lt "$deadline" ] || { cat "$root/out" >&2; exit 1; }
    sleep 0.05
done
test "$(cat "$root/run/applied")" = 7
wait "$runner"

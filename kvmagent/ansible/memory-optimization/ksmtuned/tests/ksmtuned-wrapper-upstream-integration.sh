#!/bin/bash
# End-to-end wrapper -> vendored upstream engine test with isolated proc/sysfs.
set -euo pipefail

root=$(mktemp -d)
cleanup() {
    if [ -s "$root/run/engine.pid" ]; then
        kill "$(cat "$root/run/engine.pid")" 2>/dev/null || true
    fi
    rm -rf "$root"
}
trap cleanup EXIT
mkdir -p "$root/ksm" "$root/run" "$root/etc"
cat > "$root/meminfo" <<'EOF'
MemTotal:       67108864 kB
MemFree:        67108863 kB
Buffers:             0 kB
Cached:              0 kB
EOF
printf '0\n' > "$root/ksm/run"
printf '0\n' > "$root/ksm/pages_to_scan"
printf '0\n' > "$root/ksm/sleep_millisecs"
printf '0\n' > "$root/ksm/use_zero_pages"
printf '0\n' > "$root/ksm/merge_across_nodes"
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=1
KSM_ENABLED=1
KSM_PAGES_TO_SCAN=500
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
wrapper="$(cd "$(dirname "$0")/.." && pwd)/ksmtuned-zstack"
engine="$root/upstream-engine"
cp "$(cd "$(dirname "$0")/.." && pwd)/upstream-src-ksmtuned.sh.in" "$engine"
chmod 755 "$engine"
env KSMTUNED_ENGINE="$engine" KSMTUNED_CONF="$root/conf" \
 KSMTUNED_KSM_ROOT="$root/ksm" KSMTUNED_RUNTIME_DIR="$root/run" \
 KSMTUNED_ENGINE_CONF="$root/run/engine.conf" KSMTUNED_MEMINFO="$root/meminfo" \
 KSMTUNED_LOCK="$root/run/lock" KSMTUNED_SNAPSHOT="$root/run/snapshot" KSMTUNED_MARKER="$root/run/marker" \
 KSMTUNED_APPLIED="$root/run/applied" KSMTUNED_PIDFILE="$root/run/engine.pid" \
 KSMTUNED_CONTROL_INTERVAL=0.05 "$wrapper" run >/dev/null 2>&1 &
runner=$!
wait_pages() {
    expected=$1
    deadline=$(( $(date +%s) + 10 ))
    while [ "$(cat "$root/ksm/pages_to_scan")" != "$expected" ]; do
        [ "$(date +%s)" -lt "$deadline" ] || { echo "upstream engine did not apply pages=$expected" >&2; exit 1; }
        sleep 0.1
    done
    test "$(cat "$root/ksm/sleep_millisecs")" = 20 || { echo 'effective sleep is not 20ms' >&2; exit 1; }
}
wait_pages 500
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=2
KSM_ENABLED=1
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
wait_pages 2000
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=3
KSM_ENABLED=1
KSM_PAGES_TO_SCAN=500
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
wait_pages 500
kill "$runner" 2>/dev/null || true

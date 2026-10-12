#!/bin/bash
# Execute the vendored upstream ksmtuned algorithm against an isolated fake
# proc/sysfs tree. This is an engine test, not a source grep.
set -euo pipefail

root=$(mktemp -d)
cleanup() {
    if [ -s "$root/ksmtune.pid" ]; then
        kill "$(cat "$root/ksmtune.pid")" 2>/dev/null || true
    fi
    rm -rf "$root"
}
trap cleanup EXIT
mkdir -p "$root/etc" "$root/proc" "$root/sys/kernel/mm/ksm" "$root/bin"
cat > "$root/etc/ksmtuned.conf" <<'EOF'
KSM_MONITOR_INTERVAL=0.05
KSM_NPAGES_BOOST=300
KSM_NPAGES_DECAY=-50
KSM_NPAGES_MIN=2000
KSM_NPAGES_MAX=2000
KSM_SLEEP_MSEC=80
KSM_THRES_COEF=100
KSM_THRES_CONST=2048
EOF
cat > "$root/proc/meminfo" <<'EOF'
MemTotal:       67108864 kB
MemFree:             1 kB
Buffers:             0 kB
Cached:              0 kB
EOF
printf '0\n' > "$root/sys/kernel/mm/ksm/run"
printf '0\n' > "$root/sys/kernel/mm/ksm/pages_to_scan"
printf '0\n' > "$root/sys/kernel/mm/ksm/sleep_millisecs"
cat > "$root/bin/pgrep" <<'EOF'
#!/bin/sh
echo 123
EOF
cat > "$root/bin/ps" <<'EOF'
#!/bin/sh
echo 1
EOF
chmod +x "$root/bin/pgrep" "$root/bin/ps"

engine=$(mktemp)
trap 'cleanup; rm -f "$engine"' EXIT
# Adapt filesystem locations only; execute the vendored algorithm itself.
sed -e "s#@SYSCONFDIR@#$root/etc#g" \
    -e "s#/proc/meminfo#$root/proc/meminfo#g" \
    -e "s#/sys/kernel/mm/ksm#$root/sys/kernel/mm/ksm#g" \
    -e "s#/var/run/ksmtune.pid#$root/ksmtune.pid#g" \
    "$(cd "$(dirname "$0")/.." && pwd)/upstream-src-ksmtuned.sh.in" > "$engine"
chmod +x "$engine"

PATH="$root/bin:$PATH" "$engine" >/dev/null 2>&1 &
runner=$!
deadline=$(( $(date +%s) + 5 ))
while [ "$(cat "$root/sys/kernel/mm/ksm/pages_to_scan")" != 2000 ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "upstream engine did not reach target pages before deadline" >&2
        exit 1
    fi
    sleep 0.05
done
# 64GiB with configured 80ms (inverse scaling) must produce actual 20ms;
# high pressure must raise the scan batch to the target maximum.
actual_sleep=$(cat "$root/sys/kernel/mm/ksm/sleep_millisecs")
actual_pages=$(cat "$root/sys/kernel/mm/ksm/pages_to_scan")
test "$actual_sleep" = 20 || { echo "expected actual sleep 20, got $actual_sleep" >&2; exit 1; }
test "$actual_pages" = 2000 || { echo "expected pages 2000, got $actual_pages" >&2; exit 1; }

# Relaxed pressure must retain the fixed 2000-page target; the original
# adaptive range is intentionally disabled by MIN=MAX.
cat > "$root/proc/meminfo" <<'EOF'
MemTotal:       67108864 kB
MemFree:         67108863 kB
Buffers:             0 kB
Cached:              0 kB
EOF
sleep 0.25
actual_pages=$(cat "$root/sys/kernel/mm/ksm/pages_to_scan")
test "$actual_pages" = 2000 || { echo "expected fixed pages 2000 after low pressure, got $actual_pages" >&2; exit 1; }

# The vendored script daemonizes; stop only the child recorded in its private
# pidfile. The shell launcher may already have exited successfully.
if [ -s "$root/ksmtune.pid" ]; then
    kill "$(cat "$root/ksmtune.pid")" 2>/dev/null || true
fi

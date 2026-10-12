#!/bin/bash
# Contract RED: the ownership wrapper must delegate continuous KSM policy
# writes to the vendored upstream engine instead of implementing its own loop.
set -euo pipefail

root=$(mktemp -d)
cleanup() { kill "${runner:-}" 2>/dev/null || true; rm -rf "$root"; }
trap cleanup EXIT
mkdir -p "$root/ksm" "$root/run" "$root/bin"
printf 'MemTotal:       67108864 kB\n' > "$root/meminfo"
printf '0\n' > "$root/ksm/run"
printf '0\n' > "$root/ksm/pages_to_scan"
printf '0\n' > "$root/ksm/sleep_millisecs"
printf '0\n' > "$root/ksm/use_zero_pages"
printf '1\n' > "$root/ksm/merge_across_nodes"
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=1
KSM_ENABLED=1
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
cat > "$root/engine" <<'EOF'
#!/bin/sh
echo $$ > "${KSMTUNED_PIDFILE:?}"
pages=$(sed -n 's/^KSM_NPAGES_MIN=//p' "$KSMTUNED_CONF")
sleep_ms=$(sed -n 's/^KSM_SLEEP_MSEC=//p' "$KSMTUNED_CONF")
total=$(awk '/^MemTotal:/ {print $2; exit}' "${KSMTUNED_MEMINFO:-/proc/meminfo}")
actual=$(( (sleep_ms * 16777216 + total - 1) / total ))
echo "$pages" > "$KSMTUNED_KSM_ROOT/pages_to_scan"
echo "$actual" > "$KSMTUNED_KSM_ROOT/sleep_millisecs"
echo 1 > "$KSMTUNED_KSM_ROOT/run"
echo started > "${ENGINE_MARKER:?}"
while :; do sleep 1; done
EOF
chmod +x "$root/engine"
wrapper="$(cd "$(dirname "$0")/.." && pwd)/ksmtuned-zstack"
ENGINE_MARKER="$root/engine.started" KSMTUNED_ENGINE="$root/engine" \
KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$root/ksm" \
KSMTUNED_LOCK="$root/run/lock" KSMTUNED_SNAPSHOT="$root/run/snapshot" KSMTUNED_MARKER="$root/run/marker" \
KSMTUNED_APPLIED="$root/run/applied" KSMTUNED_RUNTIME_DIR="$root/run" \
KSMTUNED_MEMINFO="$root/meminfo" KSMTUNED_CONTROL_INTERVAL=0.05 \
"$wrapper" run >/dev/null 2>&1 &
runner=$!
deadline=$(( $(date +%s) + 3 ))
while [ ! -e "$root/engine.started" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        echo "expected wrapper to invoke KSMTUNED_ENGINE; marker is missing" >&2
        if ! kill -0 "$runner" 2>/dev/null; then
            wait "$runner" || echo "wrapper exited before invoking engine" >&2
        fi
        exit 1
    fi
    sleep 0.05
done
test -s "$root/engine.started" || {
    echo "expected non-empty engine marker" >&2
    exit 1
}

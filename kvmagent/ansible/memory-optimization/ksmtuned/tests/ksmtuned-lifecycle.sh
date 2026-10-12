#!/bin/bash
set -euo pipefail

root=$(mktemp -d)
cleanup() { [ ! -s "$root/run/writer.lock.engine.pid" ] || kill "$(cat "$root/run/writer.lock.engine.pid")" 2>/dev/null || true; rm -rf "$root"; }
trap cleanup EXIT
ksm="$root/ksm"; mkdir -p "$ksm" "$root/bin" "$root/run" "$root/etc"
export KSMTUNED_RUNTIME_DIR="$root/run/memory-optimization"
export KSMTUNED_MEMINFO="$root/meminfo"
export KSMTUNED_LOCK="$root/run/default.lock"
printf 'MemTotal:       67108864 kB\n' > "$root/meminfo"
printf '1\n' > "$ksm/run"; printf '100\n' > "$ksm/pages_to_scan"
printf '20\n' > "$ksm/sleep_millisecs"; printf '1\n' > "$ksm/use_zero_pages"
printf '1\n' > "$ksm/merge_across_nodes"
cat > "$root/bin/systemctl" <<'EOF'
#!/bin/bash
state=${FAKE_SYSTEMD_STATE:?}
args=("$@")
unit=${args[${#args[@]}-1]}
key=$(echo "$unit" | tr '/.' '__')
printf '%s\n' "$*" >> "$state.calls"
enabled_file="$state.$key.enabled"
active_file="$state.$key.active"
mask_file="$state.$key.masked"
if [ "$unit" = ksmtuned.service ]; then
  enabled_file="$state.enabled"
  active_file="$state.active"
fi
if [ "$unit" = zstack-ksmtuned.service ]; then
  enabled_file="$state.managed.enabled"
  active_file="$state.managed.active"
  [ -e "$enabled_file" ] || echo enabled > "$enabled_file"
  [ -e "$active_file" ] || echo active > "$active_file"
fi
case "${args[0]}" in
  show)
    [ ! -e "$state.$key.show-fail" ] || { echo 'bus unavailable' >&2; exit 1; }
    if [ -e "$state.$key.show-output" ]; then cat "$state.$key.show-output"
    else echo 'LoadState=loaded'; fi ;;
  is-enabled)
    if [ -e "$mask_file" ]; then echo masked
    elif [ -e "$enabled_file" ]; then cat "$enabled_file"
    elif [ "$unit" = ksm.service ]; then echo disabled
    else echo not-found
    fi ;;
  is-active)
    if [ -e "$active_file" ]; then cat "$active_file"
    elif [ "$unit" = ksm.service ]; then echo inactive
    else echo not-found
    fi ;;
  enable)
    if [ "${args[1]:-}" = --runtime ]; then echo enabled-runtime > "$enabled_file"
    else echo enabled > "$enabled_file"; fi ;;
  disable) echo disabled > "$enabled_file" ;;
  mask)
    [ ! -e "$state.$key.mask-conflict" ] || { echo 'File exists'; exit 1; }
    : > "$mask_file" ;;
  unmask) rm -f "$mask_file" ;;
  daemon-reload) : ;;
  start)
    [ ! -e "$mask_file" ] || { echo 'Unit is masked'; exit 1; }
    [ ! -e "$state.$key.start-fail" ] || { echo 'injected start failure'; exit 1; }
    echo active > "$active_file"
    case "$unit" in ksm.service|ksmtuned.service)
      echo 1 > "${KSMTUNED_KSM_ROOT:?}/run"
      echo 888 > "${KSMTUNED_KSM_ROOT:?}/pages_to_scan"
      echo 30 > "${KSMTUNED_KSM_ROOT:?}/sleep_millisecs"
    esac ;;
  stop) echo inactive > "$active_file" ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$root/bin/systemctl"
cat > "$root/bin/id" <<'EOF'
#!/bin/sh
echo 0
EOF
chmod +x "$root/bin/id"
cat > "$root/engine" <<'EOF'
#!/bin/sh
echo $$ > "${KSMTUNED_PIDFILE:?}"
pages=$(sed -n 's/^KSM_NPAGES_MIN=//p' "$KSMTUNED_CONF")
echo "$pages" > "$KSMTUNED_KSM_ROOT/pages_to_scan"
echo 20 > "$KSMTUNED_KSM_ROOT/sleep_millisecs"
echo 1 > "$KSMTUNED_KSM_ROOT/run"
(while :; do sleep 1; done) &
echo $! > "${KSMTUNED_PIDFILE:?}"
exit 0
EOF
chmod +x "$root/engine"
export KSMTUNED_ENGINE="$root/engine"
echo enabled > "$root/run/unit.enabled"; echo active > "$root/run/unit.active"
echo disabled > "$root/run/unit.ksm_service.enabled"
echo inactive > "$root/run/unit.ksm_service.active"
echo loaded > "$root/run/unit.ksm_service.load"
echo loaded > "$root/run/unit.load"
echo loaded > "$root/run/unit_ksm_service.load"
echo loaded > "$root/run/unit_ksmtuned_service.load"
echo loaded > "$root/run/unit_zstack_ksmtuned_service.load"
cat > "$root/etc/ksmtuned.conf" <<'EOF'
dummy=1
EOF
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=1
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
script="$(cd "$(dirname "$0")/.." && pwd)/ksmtuned-zstack"
# Upstream clamps the effective sleep to 10ms. Reject an unreachable 1ms
# request before starting the engine rather than publishing a false ACK.
cat > "$root/conf-sleep1" <<'EOF'
CONFIG_REVISION=1
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=1
KSM_ZERO_PAGES=1
EOF
if output=$(KSMTUNED_CONF="$root/conf-sleep1" KSMTUNED_MEMINFO="$root/meminfo" \
  KSMTUNED_KSM_ROOT="$ksm" KSMTUNED_SNAPSHOT="$root/sleep1" \
  "$script" status 2>&1); then
  echo 'sleep=1 unexpectedly accepted' >&2
  exit 1
fi
echo "$output" | grep -q 'KSM_SLEEP_UNREPRESENTABLE'

# Exercise the arithmetic with a 1TiB MemTotal and a legal request; this must
# not overflow shell arithmetic or spuriously reject a representable value.
printf 'MemTotal:       1073741824 kB\n' > "$root/meminfo-1tb"
KSMTUNED_CONF="$root/conf" KSMTUNED_MEMINFO="$root/meminfo-1tb" \
  KSMTUNED_KSM_ROOT="$ksm" KSMTUNED_LOCK="$root/run/sleep1tb.lock" \
  KSMTUNED_SNAPSHOT="$root/sleep1tb" \
  "$script" status >/dev/null
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot" \
  KSMTUNED_MARKER="$root/marker" "$script" takeover
PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl mask ksm.service
PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl mask ksmtuned.service
test "$(PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl is-enabled ksm.service)" = masked
test "$(PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl is-enabled ksmtuned.service)" = masked

test "$(grep '^run=' "$root/snapshot")" = run=1
test "$(cat "$root/run/unit.active")" = inactive

env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot" \
  "$script" start >/dev/null
test "$(cat "$ksm/pages_to_scan")" = 2000
test "$(cat "$ksm/run")" = 1
test "$(cat "$ksm/merge_across_nodes")" = 1

# A legacy config without KSM_ENABLED is upgraded from native run=0 and must
# remain disabled across a wrapper restart; absence must never default to 1.
cat > "$root/conf-legacy-disabled" <<'EOF'
CONFIG_REVISION=9
KSM_PAGES_TO_SCAN=2000
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=1
EOF
printf '0\n' > "$ksm/run"
touch "$root/legacy-marker"
env KSMTUNED_CONF="$root/conf-legacy-disabled" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_MEMINFO="$root/meminfo" KSMTUNED_LOCK="$root/run/legacy.lock" \
  KSMTUNED_MARKER="$root/legacy-marker" KSMTUNED_SNAPSHOT="$root/legacy.snapshot" \
  "$script" stop >/dev/null
grep -q '^KSM_ENABLED=0$' "$root/conf-legacy-disabled"
legacy_runner=''
env KSMTUNED_CONF="$root/conf-legacy-disabled" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_MEMINFO="$root/meminfo" KSMTUNED_LOCK="$root/run/legacy.lock" \
  KSMTUNED_SNAPSHOT="$root/legacy.snapshot" KSMTUNED_CONTROL_INTERVAL=0.05 \
  "$script" run >/dev/null 2>&1 & legacy_runner=$!
sleep 0.2
test "$(cat "$ksm/run")" = 0
kill "$legacy_runner" 2>/dev/null || true
wait "$legacy_runner" 2>/dev/null || true
test -s "$root/snapshot.numa-owner"

# The first handoff consumes the pending marker, but the durable ownership
# target must survive later applies and an engine restart. A current sysfs
# value of 0 must not overwrite the captured legacy NUMA=1 choice.
printf '0\n' > "$ksm/merge_across_nodes"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot" \
  "$script" apply >/dev/null
test "$(cat "$ksm/merge_across_nodes")" = 1
test ! -e "$root/snapshot.numa-pending"
test "$(KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" "$script" status | grep -c '^cpuBudgetPercent=')" = 0

env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot" \
  "$script" legacy-resume >/dev/null
test "$(cat "$root/run/unit.ksm_service.enabled")" = disabled
test "$(cat "$root/run/unit.ksm_service.active")" = inactive
test "$(cat "$root/run/unit.enabled")" = enabled
test "$(cat "$root/run/unit.active")" = active

# A failed, empty, or duplicate systemd LoadState response must not be
# mistaken for a missing unit; recovery metadata is not published first.
for query_case in failed empty duplicate; do
  case "$query_case" in
    failed) touch "$root/run/unit.ksm_service.show-fail" ;;
    empty) : > "$root/run/unit.ksm_service.show-output" ;;
    duplicate) printf 'LoadState=loaded\nLoadState=not-found\n' > "$root/run/unit.ksm_service.show-output" ;;
  esac
  if output=$(env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
    KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
    KSMTUNED_LOCK="$root/run/query-$query_case.lock" KSMTUNED_SNAPSHOT="$root/query-$query_case.snapshot" \
    "$script" takeover 2>&1); then
    echo "$query_case LoadState query unexpectedly succeeded" >&2
    exit 1
  fi
  echo "$output" | grep -q 'KSM_NATIVE_UNIT_LOAD_STATE_UNKNOWN:ksm.service:query-error'
  test ! -e "$root/query-$query_case.snapshot"
  rm -f "$root/run/unit.ksm_service.show-fail" "$root/run/unit.ksm_service.show-output"
done

# legacy-resume validates the complete recovery record before stopping the
# managed service; malformed/duplicate state must be a side-effect-free refusal.
cat > "$root/bad-snapshot" <<'EOF'
schema=2
enabled=enabled
active=inactive
run=0
run=1
pages_to_scan=100
sleep_millisecs=20
EOF
before=$(wc -l < "$root/run/unit.calls")
if output=$(env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/bad-snapshot.lock" KSMTUNED_SNAPSHOT="$root/bad-snapshot" \
  "$script" legacy-resume 2>&1); then
  echo 'malformed recovery snapshot unexpectedly accepted' >&2
  exit 1
fi
echo "$output" | grep -q 'KSM_LEGACY_SNAPSHOT_DUPLICATE_OR_MALFORMED'
after=$(wc -l < "$root/run/unit.calls")
test "$before" = "$after"

ln -s "$root/snapshot" "$root/symlink-snapshot"
before=$(wc -l < "$root/run/unit.calls")
if output=$(env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/symlink-snapshot.lock" KSMTUNED_SNAPSHOT="$root/symlink-snapshot" \
  "$script" takeover 2>&1); then
  echo 'symlink recovery snapshot unexpectedly accepted' >&2
  exit 1
fi
echo "$output" | grep -q 'KSM_LEGACY_SNAPSHOT_SYMLINK_REJECTED'
after=$(wc -l < "$root/run/unit.calls")
test "$before" = "$after"
test "$(cat "$ksm/pages_to_scan")" = 100
test "$(cat "$ksm/sleep_millisecs")" = 20
test "$(cat "$ksm/use_zero_pages")" = 1
test "$(cat "$root/run/unit.active")" = active

# A consumed handoff must not leave a reusable snapshot behind, and an
# ExecStop arriving after legacy handoff must not disable legacy KSM.
test ! -e "$root/snapshot"
test -n "$(find "$root" -maxdepth 1 -name 'snapshot.*.used' -print -quit)"
env KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_MARKER="$root/marker" \
  KSMTUNED_STOP_MODE=disable "$script" stop >/dev/null
test "$(cat "$ksm/run")" = 1

# Only a currently-owned marker authorizes the managed stop transition.
: > "$root/marker"

env KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_MARKER="$root/marker" \
  KSMTUNED_STOP_MODE=disable "$script" stop >/dev/null
test "$(cat "$ksm/run")" = 0

# A run=1 legacy policy must be restored even when ksmtuned.service was
# inactive at takeover (ksm.service may be the owner of the sysfs switch).
printf '1\n' > "$ksm/run"
printf '77\n' > "$ksm/pages_to_scan"
echo inactive > "$root/run/unit.active"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot2" \
  KSMTUNED_MARKER="$root/marker2" "$script" takeover
test "$(cat "$root/snapshot2.numa-owner")" = 0
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot2" \
  KSMTUNED_MARKER="$root/marker2" "$script" legacy-resume >/dev/null
test "$(cat "$ksm/run")" = 1
test "$(cat "$root/run/unit.active")" = inactive

# Upgrade layout: an old snapshot may predate merge_across_nodes and leave an
# empty pending marker. An existing managed marker makes current sysfs=1 the
# only safe NUMA value to capture, and it must remain durable.
cat > "$root/snapshot4" <<'EOF'
enabled=enabled
active=inactive
run=1
pages_to_scan=77
EOF
: > "$root/snapshot4.numa-pending"
: > "$root/marker4"
printf '1\n' > "$ksm/merge_across_nodes"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot4" \
  KSMTUNED_MARKER="$root/marker4" "$script" start >/dev/null
test "$(cat "$root/snapshot4.numa-owner")" = 1
grep -q '^enabled=enabled$' "$root/snapshot4"
grep -q '^active=inactive$' "$root/snapshot4"
grep -q '^pages_to_scan=77$' "$root/snapshot4"
printf '0\n' > "$ksm/merge_across_nodes"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot4" \
  KSMTUNED_MARKER="$root/marker4" "$script" apply >/dev/null
test "$(cat "$ksm/merge_across_nodes")" = 1

# Upgrade layout with NUMA already in the old snapshot also repairs a missing
# owner file even when the pending marker is empty.
cat > "$root/snapshot5" <<'EOF'
enabled=enabled
active=inactive
run=1
merge_across_nodes=1
EOF
: > "$root/snapshot5.numa-pending"
rm -f "$root/snapshot5.numa-owner"
printf '0\n' > "$ksm/merge_across_nodes"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot5" \
  KSMTUNED_MARKER="$root/marker4" "$script" start >/dev/null
test "$(cat "$root/snapshot5.numa-owner")" = 1
test "$(cat "$ksm/merge_across_nodes")" = 1

# Static and pre-masked native units are restored exactly by explicit handoff.
echo static > "$root/run/unit.ksm_service.enabled"
echo inactive > "$root/run/unit.ksm_service.active"
: > "$root/run/unit.ksmtuned_service.masked"
echo inactive > "$root/run/unit.active"
printf '0\n' > "$ksm/run"; printf '91\n' > "$ksm/pages_to_scan"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot6" \
  KSMTUNED_MARKER="$root/marker6" "$script" takeover
PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl mask ksm.service
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot6" \
  KSMTUNED_MARKER="$root/marker6" "$script" legacy-resume >/dev/null
test "$(cat "$root/run/unit.ksm_service.enabled")" = static
test "$(PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl is-enabled ksmtuned.service)" = masked
test "$(cat "$root/run/unit.ksm_service.active")" = inactive
test "$(cat "$root/run/unit.active")" = inactive
test "$(cat "$ksm/run")" = 0
test "$(cat "$ksm/pages_to_scan")" = 91

# Unsupported state is rejected before a native writer is stopped or saved.
echo linked > "$root/run/unit.ksm_service.enabled"
echo active > "$root/run/unit.ksm_service.active"
if env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot-unknown" \
  "$script" takeover >"$root/unknown.out" 2>&1; then
  echo 'unsupported native unit state unexpectedly accepted' >&2
  exit 1
fi
grep -q 'KSM_NATIVE_UNIT_ENABLE_STATE_UNSUPPORTED:ksm.service:linked' "$root/unknown.out"
test "$(cat "$root/run/unit.ksm_service.active")" = active
test ! -e "$root/snapshot-unknown"

# Failed legacy restoration leaves its durable record and ownership marker.
echo disabled > "$root/run/unit.ksm_service.enabled"
echo active > "$root/run/unit.ksm_service.active"
echo inactive > "$root/run/unit.active"
printf '1\n' > "$ksm/run"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot7" \
  KSMTUNED_MARKER="$root/marker7" "$script" takeover
PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl mask ksm.service
: > "$root/run/unit.ksm_service.start-fail"
: > "$root/marker7"
if env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot7" \
  KSMTUNED_MARKER="$root/marker7" "$script" legacy-resume >"$root/restore-fail.out" 2>&1; then
  echo 'failed native restore unexpectedly succeeded' >&2
  exit 1
fi
grep -q 'KSM_NATIVE_UNIT_START_RESTORE_FAILED:ksm.service' "$root/restore-fail.out"
test -s "$root/snapshot7"
test -e "$root/marker7"

# Archive failure occurs after native state readback but before any marker is
# cleared. The active recovery snapshot must remain retryable and untouched.
echo disabled > "$root/run/unit.ksm_service.enabled"
echo inactive > "$root/run/unit.ksm_service.active"
echo disabled > "$root/run/unit.enabled"
echo inactive > "$root/run/unit.active"
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot8" \
  KSMTUNED_MARKER="$root/marker8" "$script" takeover
PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl mask ksm.service
PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" systemctl mask ksmtuned.service
: > "$root/marker8"
real_python=$(command -v python3)
cat > "$root/fail-archive-python" <<'EOF'
#!/bin/bash
source=$(mktemp)
cat > "$source"
if [ "${FAIL_ARCHIVE_PYTHON:-0}" = 1 ] && grep -q 'os.link(source, destination' "$source"; then
  rm -f "$source"
  echo 'injected archive fsync helper failure' >&2
  exit 19
fi
"${KSMTUNED_REAL_PYTHON:?}" "$@" < "$source"
result=$?
rm -f "$source"
exit "$result"
EOF
chmod 700 "$root/fail-archive-python"
if env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_PYTHON="$root/fail-archive-python" KSMTUNED_REAL_PYTHON="$real_python" \
  FAIL_ARCHIVE_PYTHON=1 KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot8" \
  KSMTUNED_MARKER="$root/marker8" "$script" legacy-resume >"$root/archive-fail.out" 2>&1; then
  echo 'injected archive failure unexpectedly succeeded' >&2
  exit 1
fi
grep -q 'KSM_LEGACY_SNAPSHOT_ARCHIVE_FAILED' "$root/archive-fail.out"
test -s "$root/snapshot8"
test -e "$root/marker8"
test -z "$(find "$root" -maxdepth 1 -name 'snapshot8.*.used' -print -quit)"

# Start remains usable without a product-license lease, and a stale lock file
# is recoverable with flock (unlike the old mkdir lock).
if env KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot" \
  KSMTUNED_MARKER="$root/marker" "$script" start >/dev/null 2>&1; then
  test "$(cat "$ksm/run")" = 1
else
  echo "start unexpectedly rejected a missing product-license lease" >&2
  exit 1
fi
printf 'stale lock contents\n' > "$root/run/writer.lock"
env KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot" \
  KSMTUNED_MARKER="$root/marker" "$script" start >/dev/null
test "$(cat "$ksm/run")" = 1

# A revision switch publishes config while holding the writer flock. The
# managed loop must remain alive across the switch rather than observing a
# partial policy and handing control to legacy ksmtuned.
cat > "$root/conf" <<'EOF'
CONFIG_REVISION=1
KSM_PAGES_TO_SCAN=200
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=0
EOF
env PATH="$root/bin:$PATH" FAKE_SYSTEMD_STATE="$root/run/unit" \
  KSMTUNED_CONF="$root/conf" KSMTUNED_KSM_ROOT="$ksm" \
  KSMTUNED_LOCK="$root/run/writer.lock" KSMTUNED_SNAPSHOT="$root/snapshot3" \
  KSMTUNED_MARKER="$root/marker3" KSMTUNED_CONTROL_INTERVAL=1 "$script" run >/dev/null 2>&1 &
runner=$!
sleep 2
flock "$root/run/writer.lock" -c "cat > '$root/conf' <<'EOF'
CONFIG_REVISION=2
KSM_PAGES_TO_SCAN=300
KSM_SLEEP_MILLISECS=20
KSM_ZERO_PAGES=0
EOF
"
sleep 2
kill -0 "$runner"
kill "$runner" 2>/dev/null || true
wait "$runner" 2>/dev/null || true
echo "ksmtuned lifecycle: PASS"

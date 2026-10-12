# Managed ksmtuned baseline

The managed `zstack-ksmtuned.service` is the sole KSM policy writer after
takeover. It does not start a second KSM daemon: it writes the kernel KSM
sysfs controls while preserving the distribution `ksmtuned` state for a
controlled rollback. Deployment must archive the distro script and its
copyright/license before takeover.

Baseline source: `https://github.com/ksmtuned/ksmtuned.git`
Pinned source revision: `018d0ed5876aee27b106c46c8889780d89ddcca2`
License: retain the upstream license and copyright notices when packaging.

The managed unit creates `/etc/zstack/memory-optimization/ksm-controller`
after takeover. Removing the marker is part of rollback and hands
`/sys/kernel/mm/ksm/run` back to the saved legacy service state.
`kvm.py` checks this marker before writing the legacy switch, so refreshes
cannot create two policy writers.

Configuration replacement must use the bounded flock at
`/run/zstack/memory-optimization/ksm.writer.lock`. The managed loop reads and
validates the policy under that lock. The legacy snapshot is consumed and
archived at the end of a handoff; it is not reused by a later ownership epoch.

The unit uses `ProtectSystem=full` with explicit writable exceptions for the
managed state and marker directories. This preserves the read-only system
boundary while allowing takeover/rollback metadata to be updated.

The Agent owns both distro writers (`ksm.service` and `ksmtuned.service`) for
the full managed-policy epoch. It snapshots their original enablement and
activity, stops them, and masks them from the privileged Agent process before
starting the managed unit. `KSM_ENABLED=0` means scanning is off; the managed
unit remains enabled and running to keep `/sys/kernel/mm/ksm/run` at `0` across
reboots. Pause/drain may stop the managed unit, but never release the native
unit masks.

Returning control to distro services is an explicit root-only handoff, not a
normal policy-off or pause/resume operation. After verifying the host is ready
to leave managed KSM ownership, run
`/usr/libexec/zstack/ksmtuned-zstack legacy-resume` outside the systemd unit.
It stops/disables the managed owner, restores native unit mask/enablement and
activity from the durable snapshot, restores the captured sysfs values after
native startup, and only then consumes the snapshot. If any state is unknown or
restoration fails, the command leaves the snapshot in place for retry. The
installer does not modify distro unit files, drop-ins, or `/etc/ksmtuned.conf`.

The selected upstream engine source is vendored in
`upstream-src-ksmtuned.sh.in` and packaged together with the wrapper; its
license and pinned baseline are retained. The wrapper remains the sole owner
of lifecycle handoff and durable policy acknowledgement rather than silently
replacing a vendor-owned daemon.

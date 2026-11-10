# Sansec health adapter

`/crypto/devices/health` uses PCI sysfs and the documented SDF ABI from the
P62.0.00.009 SDK. No vendor binary is distributed with the agent. Key management belongs to the
customer application; allocation, detach and HA do not invoke secure reclaim.

The adapter checks the PF identity and swcsm driver, opens an SDK device/session,
reads DeviceSerial and firmware/library versions, and runs the SM3 `abc`
known-answer test. It does not import keys, modify persistent keys or run a load
test. Passing this sample does not certify every algorithm or hardware component.

## Configuration

Install the vendor driver/library separately. Maintain the SDK configuration at
`/etc/swsds.ini`; the isolated worker runs with `/` as its working directory.
The worker uses the agent's Python interpreter. Protect the following local
adapter configuration as root-owned; it selects a native library to execute:
`/var/lib/zstack/crypto/sansec-health.json`.

The following is an illustrative schema, **not a certified hardware profile**.
Replace all identity/version fields with verified values. VF counts and timing
parameters require joint validation; the example values are not vendor defaults.
Set `compatible` to true only after the complete host/card/software combination
and use of the probe while VFs are active have been verified.

```json
{
  "libraryPath": "/opt/sansec/libswsds.so",
  "timeout": 5,
  "devices": {
    "0000:b3:00.0": {
      "serialNumber": "ACTUAL-SERIAL",
      "driverVersion": "ACTUAL-DRIVER",
      "firmwareVersion": "ACTUAL-FIRMWARE",
      "libraryVersion": "ACTUAL-LIBRARY",
      "compatible": false,
      "supportedVfCounts": [2],
      "pollInterval": 60,
      "validityPeriod": 180,
      "recoveryInterval": 120
    }
  }
}
```

Times are seconds. Require `1 <= timeout <= 30`,
`timeout < pollInterval < validityPeriod`, and `recoveryInterval >= 0`.
Supported VF counts must be explicitly supplied; the 64-VF maximum is not
interpreted as proof that every count from 1 to 64 is legal. Missing/invalid
configuration returns Unknown and does not load the SDK. A valid configuration
enables probing even when `compatible` is false; that flag controls eligibility,
not whether the diagnostic runs. Remove the configuration to disable SDK probes.

`driverVersionSource` defaults to `version`, selecting the loaded module's sysfs
`version` attribute. Drivers without MODULE_VERSION can explicitly set it to
`srcversion` and put the verified loaded module's source checksum in
`driverVersion`. These identities are distinct: there is no automatic fallback
or comparison of a version string with a source checksum. Health and split/unsplit
use the same check. The observed SJK1727 driver exposes `srcversion`, not `version`.

Device discovery reads `module/version` and falls back to `module/srcversion`
when `version` is absent, so source-checksum changes can invalidate the MN's
previous qualification. This discovery fallback does not change the strict
`driverVersionSource` check used by health and split/unsplit operations.

## Identity and selection boundary

The documented `SDF_OpenDevice` has no PCI/serial selector. `SDF_OpenDevice_Ex`
is not used because its ABI is undocumented. Before opening, the adapter requires
one selected, configured PF and an unambiguous `/dev/swcsm*` character-device layout. The
swcsm-bound PCI endpoints must be either that PF alone or the observed single-card
layout: functions 0 through 3 of one slot, all physical `1ed4:7011` devices, with
only function 0 exposing SR-IOV capacity. Only function 0 can receive the SDK result.
The split layout has one SDK node. The observed unsplit layout instead has four
`swcsm-pciN-0` through `swcsm-pciN-3` nodes of one major number, with matching
minor numbers 0 through 3, and `sriov_numvfs=0`. Only this complete four-function,
four-node layout is accepted; partial, mixed, aliased or extra nodes remain Unknown.
Additional cards, host-bound VFs, incomplete layouts or multiple SR-IOV PFs return
Unknown. The returned DeviceSerial must match the unique configured PF mapping;
firmware/library versions and the explicitly selected driver identity must match.

Do not map one card serial to several PFs or spread one SDK result across PFs.
Supporting multiple SDK-visible cards requires the vendor's documented selector
and verified PF/VF mapping. Companion functions without profiles remain Unknown;
one card-level self-test is not reported as independent tests of every function.
Generic discovery also recognizes VF ID `1001`; this does not establish another
verified SDK physical-function layout.

## Classification and isolation

| Evidence | Report |
| --- | --- |
| Requested PCI address absent from a readable, nonempty host PCI inventory | Fault |
| Verified identity/versions followed by `SDR_HARDFAIL` (`0x01000004`) | Fault |
| Verified identity/versions and SM3 digest or length differs from the standard vector | Fault |
| Verified identity/versions followed by `SDR_COMMFAIL` (`0x01000003`) or a hash-call timeout | Unknown twice; Fault on the third consecutive sample |
| SDK and SM3 test succeed, both handles close successfully | Normal; compatibility comes from the explicit profile |
| Missing/inaccessible sysfs, driver, SDK, profile, unsupported algorithm, wrong serial/version, permissions, other errors | Unknown |
| Open/session/info failure before identity verification, worker crash, or cleanup failure after an otherwise successful probe | Unknown |

An open failure alone is not sufficient to identify a damaged PF. Until the
vendor supplies a reliable selector and error classification, it remains Unknown,
even though the response document generically recommends a single confirmation.

Communication samples are spaced by at least `pollInterval`. A successful or
unknown collection, profile change, or gap of at least `validityPeriod` resets the
streak. Agent restart also resets it. KVM-agent Crypto policy owns configuration, timing and failure counters;
`zstacklib.utils.sansec_sdk` only implements the isolated SDF probe.
Existing management-node scheduling, health
expiry/recovery and HA event handling are reused; no new HA trigger is introduced.

Native calls run in a child process, bounded by `timeout` plus one second for kill
and reap. A worker still stuck after kill prevents another worker from starting.
The worker reports `Identifying`, `Probing` and `Closing` phases and replaces its
result file atomically. Only a `Probing` timeout counts toward consecutive
communication failures after identity verification; identification and cleanup
timeouts remain Unknown. Health and vendor operations reuse the existing
host-wide `sansec-device-operation` lock.

## Local validation

From the utility repository root:

```bash
PYTHONPATH="$(pwd)/kvmagent:$(pwd)/zstacklib" python3 -m pytest -o addopts='' \
  kvmagent/tests/test_crypto_plugin.py kvmagent/tests/test_sansec_health.py \
  kvmagent/tests/test_sansec_operations.py \
  zstacklib/tests/test_sansec_discovery.py -q -ra
```

The tests compile a test-only C shared library with GCC and exercise the actual
ctypes ABI and worker process, including 64-bit handles, standard-vector failure,
communication thresholds/reset, timeout, identity ambiguity and resource cleanup.
They use no real card or proprietary SDK. Real-card behavior, active-VF impact,
production timing/compatibility profiles and CI remain separate acceptance work.

Health reports expose `qualification` as `Unverified` or `Qualified`. Discovery
reports `cryptoQualification` as `DriverUnavailable` or `Unverified`; it does not
certify compatibility. The management node marks disappeared devices `Missing`.
The `compatible` configuration switch remains an operator-supplied qualification
input, not a health-report field. Worker result files live in a mode-0700 private
directory retained until the worker exits and removed after it is reaped.

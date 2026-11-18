"""
Hot-spare disks must not be reported as "Host Disk Status Abnormal".

Root cause this guards against:
  arcconf `getconfig <id> AL` reports a hot-spare with a multi-word State, e.g.
      State : Auto Replace Hot-Spare
  The collector used to keep only the first word via v.split(" ")[0] -> "Auto",
  and convert_disk_state_to_int("auto") falls through to the abnormal value 100,
  which the UI renders as Abnormal and which fires a disk-status alarm to the MN.
  sas3ircu has the same shape, reporting e.g. "Hot Spare (HSP)".

These tests pin the contract at two levels:
  1. convert_disk_state_to_int: every hot-spare spelling must map to Normal(0).
  2. collect_arcconf_raid_state / collect_sas_raid_state: end-to-end parse of a
     real hot-spare row must record physical_disk_state=0 and raise NO alarm.

Style follows test_prometheus_disk_wwid.py (import-or-skip + mock.patch.object).
"""
import unittest

try:
    from kvmagent.plugins import prometheus
except ImportError as e:
    raise unittest.SkipTest(
        "kvmagent package not importable (%s); "
        "run with PYTHONPATH=kvmagent:zstacklib" % e)

import mock

# State value contract shared with BFF disk.service.ts:
#   0 Normal | 5 Rebuilding | 10 Offline | 20 Missing | 100 Abnormal(fallback)
NORMAL, REBUILDING, OFFLINE, MISSING, ABNORMAL = 0, 5, 10, 20, 100


class TestConvertDiskStateToInt(unittest.TestCase):

    def test_hotspare_spellings_are_normal(self):
        # WHY: a hot-spare is a healthy standby; it must never be Abnormal(100),
        # otherwise the host raises a false "Host Disk Status Abnormal" alarm.
        for s in ["Auto Replace Hot-Spare", "Hot Spare", "Hot Spare (HSP)",
                  "Global Hot-Spare", "Dedicated Hot-Spare", "hot-spare",
                  "GHS", "DHS"]:
            self.assertEqual(NORMAL, prometheus.convert_disk_state_to_int(s),
                             "%r must map to Normal(0)" % s)

    def test_other_states_unchanged(self):
        # WHY: the fix widens "normal" inputs only; it must not regress the
        # states the alarm pipeline depends on.
        self.assertEqual(NORMAL, prometheus.convert_disk_state_to_int("Online"))
        self.assertEqual(NORMAL, prometheus.convert_disk_state_to_int("Optimal"))
        self.assertEqual(REBUILDING, prometheus.convert_disk_state_to_int("Rebuild"))
        self.assertEqual(OFFLINE, prometheus.convert_disk_state_to_int("Failed"))
        self.assertEqual(OFFLINE, prometheus.convert_disk_state_to_int("Offline"))
        self.assertEqual(MISSING, prometheus.convert_disk_state_to_int("Missing"))
        self.assertEqual(ABNORMAL,
                         prometheus.convert_disk_state_to_int("Predictive Failure"))

    # Exact-match short codes (==, not substring). These are storcli abbreviations
    # whose branches must keep working. Removing the v.split(" ")[0] truncation
    # leaves these unaffected, because each code is a single word (split is a
    # no-op for them); this test pins that.
    SHORTCODE_EXPECTATIONS = [
        ("Onln", NORMAL), ("GHS", NORMAL), ("DHS", NORMAL),
        ("UGood", NORMAL), ("CpyBck", NORMAL),
        ("Rbld", REBUILDING), ("Offln", OFFLINE),
    ]

    def test_exact_match_shortcodes_case_insensitive(self):
        # WHY: convert_disk_state_to_int lowercases before "==" comparison.
        # Real tools emit mixed case (Onln/GHS/Rbld/Offln); dropping .lower()
        # would silently send these to the 100/Abnormal fallback. Pin it.
        for code, expected in self.SHORTCODE_EXPECTATIONS:
            self.assertEqual(expected, prometheus.convert_disk_state_to_int(code),
                             "%r must map to %d" % (code, expected))

    def test_shortcodes_unaffected_by_removing_split(self):
        # WHY: encodes the review finding directly - for single-word short codes
        # the old truncation v.split(" ")[0] and the new full string are equal,
        # so convert() returns the same value either way.
        for code, _ in self.SHORTCODE_EXPECTATIONS:
            old_input = code.split(" ")[0].strip()  # pre-fix parsing
            new_input = code.strip()                # post-fix parsing
            self.assertEqual(
                prometheus.convert_disk_state_to_int(old_input),
                prometheus.convert_disk_state_to_int(new_input),
                "shortcode %r changed result after removing split()" % code)

    # Substring matching ("ready"/"raw"/"online" in state) checks the NORMAL
    # keywords before the failure keywords. Now that full multi-word State
    # strings reach the matcher, a failed/degraded state whose text happens to
    # contain a normal substring would be silently classified Normal - a bad
    # disk that raises no alarm. These cases are not known to be emitted by the
    # current arcconf/sas tooling, so this is a guard against regression rather
    # than an observed failure.
    FAILURE_STATES_WITH_NORMAL_SUBSTRING = [
        "Not Ready",             # contains "ready"
        "Offline - not ready",   # contains "ready" before "offline" is reached
    ]

    def test_failure_state_with_normal_substring_not_silenced(self):
        # WHY: a real bad disk must never be reported as Normal(0); that would
        # suppress the disk alarm. Pins the safety boundary the matcher must hold.
        for s in self.FAILURE_STATES_WITH_NORMAL_SUBSTRING:
            self.assertNotEqual(
                NORMAL, prometheus.convert_disk_state_to_int(s),
                "%r is a failure/degraded state and must NOT map to Normal(0); "
                "a broad substring keyword (e.g. 'ready') is masking it" % s)


# Real arcconf `getconfig <id> AL` excerpt, trimmed to the fields the parser reads.
# Device #0 = healthy data disk (Online), Device #1 = a hot-spare reporting
# "Auto Replace Hot-Spare".
ARCCONF_AL_WITH_HOTSPARE = """\
Controllers found: 1

----------------------------------------------------------------------
Logical Device Information
----------------------------------------------------------------------
   Logical Device number 0
   Status of Logical Device                 : Optimal

Physical Device information

      Device #0
         Device is a Hard drive
         State                              : Online
         Serial number                      : DATADISK0001
         Reported Location                  : Enclosure 0, Slot 2(Connector 0:I)
      Device #1
         Device is a Hard drive
         State                              : Auto Replace Hot-Spare
         Serial number                      : WAE1Y1Z7
         Reported Location                  : Enclosure 0, Slot 3(Connector 0:I)
"""


class TestCollectArcconfHotSpare(unittest.TestCase):
    """End-to-end parse: exercises the real truncation site (line ~635)."""

    def _run(self):
        metrics = {
            'raid_state': mock.MagicMock(),
            'physical_disk_state': mock.MagicMock(),
        }

        def fake_bash_ro(cmd):
            if "getconfig" in cmd:
                return 0, ARCCONF_AL_WITH_HOTSPARE
            return 0, ""

        with mock.patch.object(prometheus, "bash_ro", side_effect=fake_bash_ro), \
                mock.patch.object(prometheus, "handle_raid_state"), \
                mock.patch.object(prometheus, "check_disk_insert_and_remove"), \
                mock.patch.object(prometheus, "is_disk_status_abnormal",
                                  return_value=False), \
                mock.patch.object(prometheus, "remove_disk_status_abnormal"), \
                mock.patch.object(prometheus,
                                  "send_physical_disk_status_alarm_to_mn") as alarm:
            prometheus.collect_arcconf_raid_state(metrics, "0:Adapter")
            return metrics, alarm

    def test_hotspare_recorded_normal_and_no_alarm(self):
        metrics, alarm = self._run()

        recorded = {
            tuple(call[0][0]): call[0][1]
            for call in metrics['physical_disk_state'].add_metric.call_args_list
        }
        # Slot 3 hot-spare must be Normal(0), not Abnormal(100).
        self.assertEqual(NORMAL, recorded[("3", "0")],
                         "hot-spare physical_disk_state should be 0, got %s"
                         % recorded.get(("3", "0")))
        # Healthy data disk stays Normal too.
        self.assertEqual(NORMAL, recorded[("2", "0")])

        # WHY: the whole point of the fix - no false alarm for a hot-spare.
        for call in alarm.call_args_list:
            self.assertNotEqual("WAE1Y1Z7", call[0][0],
                                "hot-spare WAE1Y1Z7 must not raise a disk alarm")


# Real sas3ircu `display` excerpt for one hot-spare drive.
SAS_DISPLAY_HOTSPARE = """\
Enclosure #                             : 2
Slot #                                  : 3
State                                   : Hot Spare (HSP)
Serial No                               : SASHSP0001
Drive Type                              : SAS_HDD
"""


class TestCollectSasHotSpare(unittest.TestCase):
    """sas3ircu path has the same truncation (line ~684)."""

    def _run(self):
        metrics = {
            'raid_state': mock.MagicMock(),
            'physical_disk_state': mock.MagicMock(),
        }

        def fake_bash_o(cmd):
            if "display" in cmd:
                return SAS_DISPLAY_HOTSPARE
            if "status" in cmd:
                return ""
            return ""

        with mock.patch.object(prometheus, "bash_o", side_effect=fake_bash_o), \
                mock.patch.object(prometheus, "handle_raid_state"), \
                mock.patch.object(prometheus, "check_disk_insert_and_remove"), \
                mock.patch.object(prometheus, "is_disk_status_abnormal",
                                  return_value=False), \
                mock.patch.object(prometheus, "remove_disk_status_abnormal"), \
                mock.patch.object(prometheus,
                                  "send_physical_disk_status_alarm_to_mn") as alarm:
            prometheus.collect_sas_raid_state(metrics, "3")
            return metrics, alarm

    def test_hotspare_recorded_normal_and_no_alarm(self):
        metrics, alarm = self._run()

        recorded = {
            tuple(call[0][0]): call[0][1]
            for call in metrics['physical_disk_state'].add_metric.call_args_list
        }
        self.assertEqual(NORMAL, recorded[("3", "2")],
                         "sas hot-spare physical_disk_state should be 0, got %s"
                         % recorded.get(("3", "2")))
        for call in alarm.call_args_list:
            self.assertNotEqual("SASHSP0001", call[0][0],
                                "sas hot-spare must not raise a disk alarm")


if __name__ == "__main__":
    unittest.main(verbosity=2)

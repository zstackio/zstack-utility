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
import json
import unittest
from unittest import mock

try:
    from kvmagent.plugins import prometheus
except ImportError as e:
    raise unittest.SkipTest(
        "kvmagent package not importable (%s); "
        "run with PYTHONPATH=kvmagent:zstacklib" % e)


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


class TestMegaRaidInventory(unittest.TestCase):
    def setUp(self):
        self.metrics = {'physical_disk_state': mock.Mock(), 'raid_state': mock.Mock()}
        self.patch("GaugeMetricFamily").side_effect = lambda name, *args: self.metrics[name]
        patcher = mock.patch.object(prometheus, "mega_raid_inventory", prometheus.MegaRaidDiskInventory())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.status = self.patch("send_physical_disk_status_alarm_to_mn")
        self.insert = self.patch("send_physical_disk_insert_alarm_to_mn")
        self.remove = self.patch("send_physical_disk_remove_alarm_to_mn")
        self.virtual = self.patch("bash_ro")
        self.physical = self.patch("bash_roe")

    def patch(self, name):
        patcher = mock.patch.object(prometheus, name)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def controller(self, index, drives=(), status="Success"):
        data = {}
        for slot, sn, state in drives:
            drive = "Drive /c%s/e1/s%s" % (index, slot)
            data[drive] = [{"State": state}]
            attrs = {} if sn is None else {"SN": sn}
            data[drive + " - Detailed Information"] = {drive + " Device attributes": attrs}
        return {"Command Status": {"Controller": index, "Status": status}, "Response Data": data}

    def poll(self, controllers, rc=0, virtual=None, virtual_rc=0, output=None):
        if virtual is None:
            virtual = [self.controller(c["Command Status"]["Controller"]) for c in controllers]
        vd = json.dumps({"Controllers": virtual})
        self.virtual.side_effect = lambda cmd: (virtual_rc, vd) if "/vall" in cmd else (1, "")
        if output is None:
            output = json.dumps({"Controllers": controllers})
        self.physical.return_value = (rc, output, "")
        return prometheus.collect_raid_state()

    def disks(self, *names):
        return self.controller(0, [
            (ord(name) - ord("A"), name, "Onln") for name in names])

    def test_offline_on_successful_card_survives_peer_failure(self):
        good = self.controller(1, [(2, "B", "Offln")])
        bad = self.controller(0, status="Failure")
        for controllers in ([bad, good], [good, bad]):
            for rc in (0, 45):
                self.status.reset_mock()
                self.poll(controllers, rc)
                self.status.assert_called_once_with("B", "2", "1", OFFLINE)
                self.metrics["physical_disk_state"].add_metric.assert_called_with(["2", "1"], OFFLINE)

    def test_virtual_query_with_failed_first_card_still_collects_offline_disk(self):
        good = self.controller(1, [(2, "B", "Offln")])
        bad = self.controller(0, status="Failure")
        self.poll([bad, good], 45, virtual=[bad, self.controller(1)], virtual_rc=45)
        self.status.assert_called_once_with("B", "2", "1", OFFLINE)

    def test_failed_virtual_query_still_reports_known_physical_status(self):
        self.poll([self.disks("A", "B")])
        for _ in range(3):
            good = self.controller(1, [(2, "C", "Offln")])
            self.poll([good], virtual=[self.controller(0, status="Failure")], virtual_rc=45)
        self.assertEqual([mock.call("C", "2", "1", OFFLINE)] * 3, self.status.call_args_list)
        self.insert.assert_not_called()
        self.remove.assert_not_called()

    def test_failed_storcli_without_usable_data_falls_back_to_arcconf(self):
        vd = json.dumps({"Controllers": [self.controller(0)]})

        def result(cmd):
            if "arcconf list" in cmd:
                return 0, "1: Adapter"
            return (45, vd) if "/vall" in cmd else (1, "")

        self.virtual.side_effect = result
        self.physical.return_value = (45, "", "")
        arcconf = self.patch("collect_arcconf_raid_state")
        self.assertIs(arcconf.return_value, prometheus.collect_raid_state())
        arcconf.assert_called_once_with(self.metrics, "1: Adapter")

    def test_invalid_controller_id_preserves_peer_status(self):
        good = self.controller(1, [(2, "B", "Offln")])
        for invalid_id in ([], {}, "["):
            self.status.reset_mock()
            self.poll([self.controller(invalid_id), good])
            self.status.assert_called_once_with("B", "2", "1", OFFLINE)

    def test_unrelated_changes_do_not_restart_missing_serial_count(self):
        self.poll([self.disks("A", "B")])
        self.insert.assert_not_called()
        self.poll([self.disks("B", "C")])
        self.insert.assert_called_once_with("C", "1-2")
        self.poll([self.disks("B")])
        self.remove.assert_not_called()
        self.poll([self.disks("B", "D")])
        self.remove.assert_called_once_with("A", "1-0")
        self.poll([self.disks("B", "D")])
        self.assertEqual([mock.call("A", "1-0"), mock.call("C", "1-2")], self.remove.call_args_list)
        self.poll([self.disks("A", "B", "C", "D")])
        self.insert.assert_has_calls([mock.call("A", "1-0"), mock.call("C", "1-2")], any_order=True)

    def test_reappearing_disk_resets_only_its_own_count(self):
        self.poll([self.disks("A", "B", "C")])
        self.poll([self.disks("C")])
        self.poll([self.disks("A", "C")])
        self.poll([self.disks("C")])
        self.remove.assert_called_once_with("B", "1-1")
        self.poll([self.disks("C")])
        self.remove.assert_called_once_with("B", "1-1")
        self.poll([self.disks("C")])
        self.assertEqual(mock.call("A", "1-0"), self.remove.call_args_list[-1])
        self.insert.assert_not_called()

    def test_incomplete_polls_leave_pending_count_and_baseline_untouched(self):
        a = self.disks("A", "B")
        b = self.disks("B")
        self.poll([a])
        self.poll([b])
        for output in ("", " ", "bad JSON", '{"Controllers": []}'):
            self.poll([b], output=output)
        for _ in range(3):
            self.poll([self.disks("B", "C")], rc=45)
            self.poll([self.disks("B", "C"), self.controller(1, status="Failure")])
            self.poll([self.disks("B", "C"), self.controller(1)])
        self.insert.assert_not_called()
        self.remove.assert_not_called()
        self.poll([b])
        self.remove.assert_not_called()
        self.poll([b])
        self.remove.assert_called_once_with("A", "1-0")

    def test_partial_drive_rows_and_omitted_controller_preserve_known_disks(self):
        a = self.controller(0, [(0, "A", "Onln")])
        b = self.controller(1, [(1, "B", "Offln")])
        self.poll([a, b])
        for _ in range(3):
            self.poll([b], virtual=[self.controller(0), self.controller(1)])
            partial = self.controller(0, [(0, "A", "Onln"), (2, "C", "Onln")])
            del partial["Response Data"]["Drive /c0/e1/s0"]
            self.poll([partial, b])
        self.insert.assert_not_called()
        self.remove.assert_not_called()
        self.assertEqual(7, self.status.call_count)

    def test_controller_omitted_from_both_queries_freezes_only_inventory(self):
        peer = self.controller(1, [(2, "C", "Onln")])
        self.poll([self.disks("A", "B"), peer])
        self.poll([self.disks("B"), peer])

        partial = self.controller(0, [(1, "B", "Offln"), (3, "D", "Onln")])
        for _ in range(3):
            self.poll([partial])
        self.remove.assert_not_called()
        self.insert.assert_not_called()
        self.assertEqual([mock.call("B", "1", "1", OFFLINE)] * 3, self.status.call_args_list)

        self.poll([self.disks("B"), peer])
        self.remove.assert_not_called()
        self.poll([self.disks("B"), peer])
        self.remove.assert_called_once_with("A", "1-0")
        self.insert.assert_not_called()

    def test_new_controller_is_confirmed_only_in_a_complete_poll(self):
        first = self.disks("A")
        second = self.controller(1, [(1, "B", "Onln")])
        third = self.controller(2, [(2, "C", "Onln")])
        self.poll([first])
        self.poll([first, second])
        self.insert.assert_called_once_with("B", "1-1")

        for _ in range(3):
            self.poll([first, third])
        self.insert.assert_called_once_with("B", "1-1")
        self.remove.assert_not_called()
        self.poll([first, second, third])
        self.assertEqual([mock.call("B", "1-1"), mock.call("C", "1-2")], self.insert.call_args_list)

    def test_bad_virtual_drive_row_keeps_peer_physical_status(self):
        bad = self.controller(0)
        bad["Response Data"]["/c0/v0"] = [{"State": None, "DG/VD": "0/0"}]
        good = self.controller(1, [(1, "B", "Offln")])
        self.poll([good], virtual=[bad, self.controller(1)])
        self.status.assert_called_once_with("B", "1", "1", OFFLINE)

    def test_degraded_virtual_drive_alongside_incomplete_disk_inventory(self):
        virtual = self.controller(0)
        virtual["Response Data"]["/c0/v2"] = [{"State": "Dgrd", "DG/VD": "4/2"}]
        raid_alarm = self.patch("send_raid_state_alarm_to_mn")
        self.poll([self.controller(0, status="Failure")], rc=45, virtual=[virtual])
        self.metrics["raid_state"].add_metric.assert_called_once_with(["4"], 5)
        raid_alarm.assert_called_once_with("4", "Dgrd")

    def test_virtual_drive_id_fallback_accepts_numeric_ids_and_skips_invalid_rows(self):
        virtual = self.controller(0)
        virtual["Response Data"]["/c0/v1"] = [{"State": "Dgrd", "VD": 1}]
        virtual["Response Data"]["/c0/v2"] = [{"State": "Optl", "VD": []}]
        self.patch("send_raid_state_alarm_to_mn")
        self.poll([self.controller(0, [(1, "B", "Offln")])], virtual=[virtual])
        self.metrics["raid_state"].add_metric.assert_called_once_with([1], 5)
        self.status.assert_called_once_with("B", "1", "1", OFFLINE)

    def test_blank_serial_keeps_other_status_and_blocks_inventory(self):
        self.poll([self.disks("A", "B")])
        for serial in (None, "", " \t "):
            self.status.reset_mock()
            self.metrics["physical_disk_state"].reset_mock()
            good = self.controller(0, [(0, serial, "Onln"), (1, u"B\u03a9", "Offln")])
            self.poll([good])
            self.status.assert_called_once_with(u"B\u03a9", "1", "1", OFFLINE)
            self.metrics["physical_disk_state"].add_metric.assert_has_calls(
                [mock.call(["0", "1"], NORMAL), mock.call(["1", "1"], OFFLINE)], any_order=True)
        self.insert.assert_not_called()
        self.remove.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)

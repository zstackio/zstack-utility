import threading
import unittest
from unittest import mock

from kvmagent.plugins import ha_plugin
from kvmagent.plugins.ha_plugin import HaPlugin


def _make_plugin():
    plugin = HaPlugin.__new__(HaPlugin)
    plugin.ha_network_group_lock = threading.RLock()
    plugin.ha_network_group_last_status = {}
    plugin.ha_network_group_reporting_in_flight = False
    plugin.ha_network_group_report_generation = 0
    return plugin


def _vm_rule(min_score=2):
    return {
        'groups': {
            'group-1': {
                'rules': [
                    {'resource': 'eth0', 'weight': 1},
                    {'resource': 'eth1', 'weight': 1},
                ],
                'minScore': min_score,
            }
        }
    }


class TestHaNetworkGroupFailedVmReporting(unittest.TestCase):
    def setUp(self):
        self.plugin = _make_plugin()

    @mock.patch.object(ha_plugin, 'clean_network_config')
    @mock.patch.object(ha_plugin, 'kill_vm_use_pid')
    @mock.patch.object(ha_plugin.linux, 'get_vm_pid', return_value='1234')
    def test_failed_vm_is_collected_without_kill_or_network_cleanup(self, get_pid, kill_vm, clean_network):
        self.plugin._get_vm_enable_ha = mock.Mock(return_value=True)

        failed = self.plugin._collect_failed_vms_by_network_group_rule(
            {'vm-b': _vm_rule(), 'vm-a': _vm_rule()}, {'eth0'})

        self.assertEqual(['vm-a', 'vm-b'], failed)
        self.assertEqual(2, get_pid.call_count)
        kill_vm.assert_not_called()
        clean_network.assert_not_called()

    @mock.patch.object(ha_plugin, 'clean_network_config')
    @mock.patch.object(ha_plugin, 'kill_vm_use_pid')
    @mock.patch.object(ha_plugin.linux, 'get_vm_pid')
    def test_vm_without_qemu_or_enable_ha_is_not_reported(self, get_pid, kill_vm, clean_network):
        get_pid.side_effect = lambda vm_uuid: None if vm_uuid == 'vm-no-qemu' else '2345'
        self.plugin._get_vm_enable_ha = mock.Mock(return_value=False)

        failed = self.plugin._collect_failed_vms_by_network_group_rule(
            {'vm-no-qemu': _vm_rule(), 'vm-ha-disabled': _vm_rule()}, {'eth0'})

        self.assertEqual([], failed)
        kill_vm.assert_not_called()
        clean_network.assert_not_called()

    @mock.patch.object(ha_plugin.linux, 'get_vm_pid', return_value='1234')
    def test_vm_above_threshold_is_not_reported(self, _get_pid):
        self.plugin._get_vm_enable_ha = mock.Mock(return_value=True)

        failed = self.plugin._collect_failed_vms_by_network_group_rule(
            {'vm-1': _vm_rule(min_score=1)}, {'eth0'})

        self.assertEqual([], failed)

    def test_non_empty_failed_list_is_reported_each_fencer_cycle(self):
        reports = []

        def complete_report(status, failed_vm_uuids, generation):
            reports.append((status, failed_vm_uuids, generation))
            self.plugin.ha_network_group_last_status = dict(status)
            self.plugin.ha_network_group_reporting_in_flight = False

        self.plugin._async_report_ha_network_group_status = complete_report

        self.plugin._report_ha_network_group_status({'group-1': 'Down'}, ['vm-1'])
        self.plugin._report_ha_network_group_status({'group-1': 'Down'}, ['vm-1'])

        self.assertEqual(2, len(reports))
        self.assertEqual(['vm-1'], reports[0][1])
        self.assertEqual(['vm-1'], reports[1][1])

    def test_unchanged_status_without_failed_vm_is_not_reported(self):
        self.plugin.ha_network_group_last_status = {'group-1': 'Available'}
        self.plugin._async_report_ha_network_group_status = mock.Mock()

        self.plugin._report_ha_network_group_status({'group-1': 'Available'}, [])

        self.plugin._async_report_ha_network_group_status.assert_not_called()

    def test_http_in_flight_skips_concurrent_report(self):
        self.plugin.ha_network_group_reporting_in_flight = True
        self.plugin._async_report_ha_network_group_status = mock.Mock()

        self.plugin._report_ha_network_group_status({'group-1': 'Down'}, ['vm-1'])

        self.plugin._async_report_ha_network_group_status.assert_not_called()

    @mock.patch.object(ha_plugin.http, 'json_dump_post', side_effect=RuntimeError('mn unavailable'))
    def test_http_failure_releases_in_flight_for_next_cycle(self, _post):
        self.plugin._get_report_url_and_host_uuid = mock.Mock(return_value=('http://mn/report', 'host-1'))
        self.plugin._dump_ha_network_group_debug = mock.Mock()
        self.plugin.ha_network_group_reporting_in_flight = True

        self.plugin._do_report_ha_network_group_status({'group-1': 'Down'}, ['vm-1'], 0)

        self.assertFalse(self.plugin.ha_network_group_reporting_in_flight)
        self.plugin._async_report_ha_network_group_status = mock.Mock()
        self.plugin._report_ha_network_group_status({'group-1': 'Down'}, ['vm-1'])
        self.plugin._async_report_ha_network_group_status.assert_called_once()

    def test_restart_recalculates_and_reports_current_status(self):
        restarted = _make_plugin()
        restarted._async_report_ha_network_group_status = mock.Mock()

        restarted._report_ha_network_group_status({'group-1': 'Available'}, [])

        restarted._async_report_ha_network_group_status.assert_called_once()

    @mock.patch.object(ha_plugin.http, 'json_dump_post')
    def test_report_command_contains_sorted_deduplicated_failed_vm_uuids(self, post):
        self.plugin._get_report_url_and_host_uuid = mock.Mock(return_value=('http://mn/report', 'host-1'))
        self.plugin._dump_ha_network_group_debug = mock.Mock()

        self.plugin._do_report_ha_network_group_status(
            {'group-1': 'Down'}, ['vm-b', 'vm-a', 'vm-a'], 0)

        cmd = post.call_args[0][1]
        self.assertEqual('host-1', cmd.hostUuid)
        self.assertEqual({'group-1': 'Down'}, cmd.networkGroupStatus)
        self.assertEqual(['vm-a', 'vm-b'], cmd.failedVmUuids)


if __name__ == '__main__':
    unittest.main()

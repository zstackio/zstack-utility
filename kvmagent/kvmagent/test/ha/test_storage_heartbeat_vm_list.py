import json
import os
import tempfile
import unittest
import uuid
from unittest import mock

from kvmagent.plugins import ha_plugin


VM_UUID = '0123456789ab4def8123456789abcdef'
VHOST_PATH = '/var/run/bdc-cluster/'
CONTROLLERS = (ha_plugin.IscsiHeartbeatController, ha_plugin.CbdHeartbeatController)


def domain_xml(vm_uuid, disks, pid):
    domain = '<domain><uuid>%s</uuid><devices>%s</devices></domain>' % (vm_uuid, disks)
    return '<domstatus state="paused" pid="%s">%s</domstatus>' % (pid, domain)


def heartbeat_status(timestamp):
    return ha_plugin.jsonobject.loads(json.dumps({'heartbeat_time': timestamp, 'vm_uuids': []}))


def check_request(**overrides):
    command = {
        'interval': 0,
        'times': 1,
        'primaryStorageUuid': 'ps-uuid',
        'hostUuid': 'host-uuid',
        'hostId': 1,
        'storageCheckerTimeout': 0,
        'heartbeatUrl': 'iscsi://heartbeat',
    }
    command.update(overrides)
    return {'body': json.dumps(command)}


class TestStorageVmUsage(unittest.TestCase):
    def setUp(self):
        runtime_dir = tempfile.TemporaryDirectory()
        self.addCleanup(runtime_dir.cleanup)
        self.runtime_dir = runtime_dir.name
        self.pids = {}
        self.running_pids = set()
        patchers = [mock.patch.object(ha_plugin, 'LIVE_LIBVIRT_XML_DIR', self.runtime_dir),
                    mock.patch.object(ha_plugin.linux, 'get_vm_pid', side_effect=lambda vm: self.pids.get(vm, '')),
                    mock.patch.object(ha_plugin.linux, 'process_exists', side_effect=lambda pid: pid in self.running_pids)]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.plugin = ha_plugin.HaPlugin()
        self.plugin.storage_covering_paths = {'xinfini': [VHOST_PATH], 'other': ['/var/run/bdc-other/']}

    def write_xml(self, vm_uuid, disks, pid='42', running=True):
        with open(os.path.join(self.runtime_dir, vm_uuid + '.xml'), 'w') as fd:
            fd.write(domain_xml(vm_uuid, disks, pid))
        self.pids[vm_uuid] = pid
        if running:
            self.running_pids.add(pid)

    def unused_storages(self, ps_uuids):
        rsp = json.loads(self.plugin.check_storage_vm_usage(check_request(primaryStorageUuids=ps_uuids)))
        self.assertTrue(rsp['success'])
        return rsp['unusedPrimaryStorageUuids']

    def test_data_disk_keeps_its_storage_in_use(self):
        for attr in ha_plugin.DISK_SOURCE_ATTRIBUTES:
            with self.subTest(attr=attr):
                self.write_xml(VM_UUID, '<disk><source dev="/dev/sblk/root"/></disk>'
                               '<disk><source %s="%svolume-data"/></disk>' % (attr, VHOST_PATH))
                self.assertEqual(['other'], self.unused_storages(['xinfini', 'other']))

    def test_stopped_vm_does_not_keep_its_storage_in_use(self):
        self.write_xml(VM_UUID, '<disk><source path="%svolume-data"/></disk>' % VHOST_PATH, running=False)
        self.assertEqual(['xinfini'], self.unused_storages(['xinfini']))

    def test_storage_without_fencer_covering_paths_stays_fenced(self):
        self.write_xml(VM_UUID, '<disk><source dev="/dev/sblk/root"/></disk>')
        with mock.patch.object(ha_plugin.etree, 'parse') as parse:
            self.assertEqual([], self.unused_storages(['no-fencer']))
        parse.assert_not_called()

    def test_each_domain_xml_is_read_once_for_all_requested_storages(self):
        for n in range(1, 1001):
            self.write_xml(uuid.UUID(int=n, version=4).hex, '<disk><source dev="/dev/sblk/root"/></disk>', str(n))
        with mock.patch.object(ha_plugin.etree, 'parse', wraps=ha_plugin.etree.parse) as parse:
            self.assertEqual({'xinfini', 'other'}, set(self.unused_storages(['xinfini', 'other'])))
            self.assertEqual(1000, parse.call_count)

    def test_incomplete_disk_evidence_keeps_the_fence(self):
        for disks in ['<disk><source/></disk>', '<disk/>']:
            with self.subTest(disks=disks):
                self.write_xml(VM_UUID, disks)
                self.assertEqual([], self.unused_storages(['xinfini']))
        with open(os.path.join(self.runtime_dir, VM_UUID + '.xml'), 'w') as fd:
            fd.write('<domstatus')
        self.assertEqual([], self.unused_storages(['xinfini']))


class TestStorageHeartbeatNodeUsage(unittest.TestCase):
    def test_heartbeat_writes_do_not_probe_vm_usage(self):
        for controller_type in CONTROLLERS:
            for roots in ([], [VM_UUID]):
                with self.subTest(controller=controller_type, roots=roots):
                    controller = controller_type(1, 3, 'ps-uuid', [])
                    controller.covering_paths = [VHOST_PATH]
                    controller.heartbeat_path = '/heartbeat'
                    controller._heartbeat_io_check = mock.Mock(return_value=True)
                    with mock.patch.object(ha_plugin, 'find_ps_running_vm', return_value=roots), \
                            mock.patch.object(ha_plugin, 'get_running_vm_disk_paths') as probe, \
                            mock.patch.object(ha_plugin.linux, 'write_to_temp_file', return_value='/tmp/hb') as write, \
                            mock.patch.object(ha_plugin.linux, 'rm_file_force'), \
                            mock.patch.object(ha_plugin.bash, 'bash_roe', return_value=(0, '', '')):
                        self.assertTrue(controller.write_fencer_heartbeat())
                    probe.assert_not_called()
                    data = json.loads(write.call_args[0][0].split(ha_plugin.EOF)[0])
                    self.assertEqual({'heartbeat_time', 'vm_uuids'}, set(data))
                    self.assertEqual(roots, data['vm_uuids'])

    def test_iscsi_reader_uses_timestamps_with_an_empty_root_vm_list(self):
        for timestamps, updating in [([1, 2], True), ([1, 1, 1], False)]:
            with self.subTest(timestamps=timestamps):
                controller = ha_plugin.IscsiHeartbeatController(0, 1, 'ps-uuid', [])
                samples = [heartbeat_status(timestamp) for timestamp in timestamps]
                with mock.patch.object(controller, '_read_heartbeat_file', side_effect=samples), \
                        mock.patch.object(ha_plugin.time, 'sleep'):
                    self.assertEqual((updating, []), controller.check_fencer_heartbeat(1, 0, 0, 1, 'ps-uuid'))

    def test_unreadable_or_missing_timestamp_cannot_confirm_a_stopped_heartbeat(self):
        for sample in [IOError('read failed'), heartbeat_status(None)]:
            with self.subTest(sample=sample):
                with mock.patch.object(ha_plugin.IscsiHeartbeatController, '_read_heartbeat_file',
                                       side_effect=[heartbeat_status(1), sample, sample]), \
                        mock.patch.object(ha_plugin, 'login_heartbeat_path', return_value='/heartbeat'), \
                        mock.patch.object(ha_plugin.time, 'sleep'), \
                        self.assertRaises((IOError, ValueError)):
                    ha_plugin.HaPlugin().iscsi_check_vmstate(check_request())


if __name__ == '__main__':
    unittest.main()

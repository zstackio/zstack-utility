import unittest
try:
    from unittest import mock
except ImportError:
    import mock

from kvmagent.plugins import storage_device
from zstacklib.utils import lvm


class TestFcScan(unittest.TestCase):
    def patch(self, obj, name, **kwargs):
        patcher = mock.patch.object(obj, name, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def block(self, name, size='104857600'):
        return ('NAME="/dev/%s" VENDOR="TEST" MODEL="Test Disk" WWN="0x6001" '
                'SERIAL="6001" HCTL="1:0:1:0" TYPE="disk" SIZE="%s" TRAN="fc"') % (name, size)

    def test_lsblk_snapshot_preserves_fields_and_missing_device_falls_back(self):
        query = self.patch(lvm.bash, 'bash_roe', return_value=(0, self.block('sda') + '\n' + self.block('sdb'), ''))
        infos = lvm.get_lsblk_infos()
        for dev in ['sda', 'sdb']:
            info = lvm.lsblk_info(dev, infos)
            self.assertEqual('/dev/' + dev, info.name)
            self.assertEqual('Test Disk', info.model)
            self.assertEqual('104857600', info.size)
            self.assertEqual('fc', info.transport)
        self.assertEqual(1, query.call_count, 'snapshot must be queried only once')
        query.return_value = (0, self.block('sdc'), '')
        self.assertEqual('/dev/sdc', lvm.lsblk_info('sdc', infos).name)
        self.assertEqual(2, query.call_count)

    def test_bulk_paths_preserve_first_by_path_and_absent_links(self):
        self.patch(lvm.bash, 'bash_roe', return_value=(0,
                   'P: /devices/a\nN: sda\nS: disk/by-id/scsi-a\nS: disk/by-path/fc-first\nS: disk/by-path/fc-second\n\n'
                   'P: /devices/b\nN: sdb\nS: disk/by-id/scsi-b\n', ''))
        fallback = self.patch(lvm.shell, 'call', return_value='disk/by-path/fc-fallback')
        paths = lvm.get_device_paths()
        self.assertEqual('fc-first', lvm.get_device_path('sda', paths))
        self.assertEqual('fc-first', lvm.get_device_path('/dev/sda', paths))
        self.assertIsNone(lvm.get_device_path('sdb', paths))
        self.assertIsNone(lvm.get_device_path('/dev/sdb', paths))
        fallback.assert_not_called()
        self.assertEqual('fc-fallback', lvm.get_device_path('sdc', paths))
        self.assertEqual('fc-fallback', lvm.get_device_path('/dev/disk/by-id/scsi-c', paths))
        fallback.assert_called_with('udevadm info -q symlink -n /dev/disk/by-id/scsi-c')

    def test_lsblk_preserves_equals_in_device_fields(self):
        output = self.block('sda').replace('Test Disk', 'Test=Disk=A').replace('SERIAL="6001"', 'SERIAL="ID=6001"')
        self.patch(lvm.bash, 'bash_roe', return_value=(0, output, ''))
        cached = lvm.lsblk_info('sda', lvm.get_lsblk_infos())
        single = lvm.lsblk_info('sda')
        for info in [cached, single]:
            self.assertEqual('Test=Disk=A', info.model)
            self.assertEqual('ID=6001', info.serial)

    def test_malformed_lsblk_record_does_not_discard_other_devices(self):
        output = '\n'.join([self.block('sda'), 'NAME="/dev/sdb" MODEL', self.block('sdc')])
        query = self.patch(lvm.bash, 'bash_roe', return_value=(0, output, ''))
        infos = lvm.get_lsblk_infos()
        self.assertEqual({'sda', 'sdc'}, set(infos))
        for dev in ['sda', 'sdc']:
            self.assertEqual('/dev/' + dev, lvm.lsblk_info(dev, infos).name)
        self.assertEqual(1, query.call_count, 'valid records must remain cached')
        query.return_value = (0, self.block('sdb'), '')
        self.assertEqual('/dev/sdb', lvm.lsblk_info('sdb', infos).name)
        self.assertEqual(2, query.call_count, 'only the malformed record needs a single-device query')

    def test_bulk_fc_wwnn_uses_target_not_lun(self):
        self.patch(lvm.bash, 'bash_roe', return_value=(0,
                   'Class Device = "0:1"\n node_name = "0x111"\n Device = "target1:0:1"\n'
                   'Class Device = "0:2"\n node_name = "0x222"\n Device = "target1:0:2"\n', ''))
        nodes = lvm.get_storage_wwnns()
        self.assertEqual('0x111', lvm.get_storage_wwnn('1:0:1:99', nodes))
        self.assertEqual('0x222', lvm.get_storage_wwnn('1:0:2:0', nodes))

    def test_failed_snapshots_keep_single_device_queries_available(self):
        query = self.patch(lvm.bash, 'bash_roe', return_value=(1, '', 'error'))
        self.assertIsNone(lvm.get_lsblk_infos())
        self.assertIsNone(lvm.get_device_paths())
        self.assertIsNone(lvm.get_storage_wwnns())
        query.return_value = (0, self.block('sda'), '')
        self.assertEqual('/dev/sda', lvm.lsblk_info('sda', None).name)
        self.patch(lvm.shell, 'call', return_value='"0x123"')
        self.assertEqual('0x123', lvm.get_storage_wwnn('1:0:1:0', None))

    def test_multipath_cache_misses_preserve_single_device_judgment(self):
        query = self.patch(lvm.bash, 'bash_roe', return_value=(0, 'sda mpatha\nsdb [orphan]\n', ''))
        check = self.patch(lvm.bash, 'bash_r')
        slaves = lvm.get_multipath_slaves()
        self.assertTrue(lvm.is_slave_of_multipath('/dev/sda', slaves, True))
        self.assertFalse(lvm.is_slave_of_multipath('/dev/sda', slaves, False))
        self.assertFalse(lvm.is_slave_of_multipath('/dev/sdb', slaves, False))
        check.assert_not_called()
        query.return_value = (0, '', '')
        empty = lvm.get_multipath_slaves()
        for dev, snapshot in [('/dev/sdb', slaves), ('/dev/sdc', slaves), ('/dev/sda', empty)]:
            for rc in [0, 1]:
                check.reset_mock()
                check.return_value = rc
                original = lvm.is_slave_of_multipath(dev, None, True)
                cached = lvm.is_slave_of_multipath(dev, snapshot, True)
                self.assertEqual(rc == 0, cached)
                self.assertEqual(original, cached, 'missing maps must not change the multipath judgment')
                self.assertEqual([mock.call('multipath -c ' + dev)] * 2, check.call_args_list)

    def test_multipath_query_failure_falls_back_without_rechecking_service(self):
        query = self.patch(lvm.bash, 'bash_roe')
        check = self.patch(lvm.bash, 'bash_r', return_value=0)
        for result in [(124, '', 'timeout'), (1, '', 'error'), (0, 'fail\n', '')]:
            query.return_value = result
            slaves = lvm.get_multipath_slaves()
            self.assertIsNone(slaves)
            self.assertTrue(lvm.is_slave_of_multipath('/dev/sda', slaves, True))
        self.assertEqual([mock.call('multipath -c /dev/sda')] * 3, check.call_args_list)

    def test_fc_scan_rescans_before_snapshot_and_collects_once(self):
        events = []
        commands = []
        self.patch(storage_device.bash, 'bash_o', return_value='1:0:1\n2:0:1\n')
        scsi = self.patch(lvm, 'run_lsscsi_i', return_value=[
            '[1:0:1:0] disk TEST /dev/sda 36001', '[2:0:1:0] disk TEST /dev/sdb 36002'])
        self.patch(storage_device.linux, 'write_file', side_effect=lambda path, value: events.append(path))
        running = self.patch(lvm, 'is_multipath_running', return_value=True)
        check = self.patch(lvm.bash, 'bash_r', return_value=1)

        def query(cmd, *args, **kwargs):
            commands.append(cmd)
            if cmd.startswith('lsblk'):
                self.assertEqual(2, len(events), 'all size rescans must precede the lsblk snapshot')
                return 0, self.block('sda', '209715200') + '\n' + self.block('sdb', '209715200'), ''
            if cmd.startswith('udevadm'):
                return 0, 'N: sda\nS: disk/by-path/fc-a\n\nN: sdb\nS: disk/by-path/fc-b\n', ''
            if cmd.startswith('systool'):
                return 0, 'node_name = "0x111"\nDevice = "target1:0:1"\n', ''
            if 'multipathd show paths' in cmd:
                return 0, 'sda mpatha\nsdb [orphan]\n', ''
            self.fail('unexpected command: ' + cmd)

        self.patch(lvm.bash, 'bash_roe', side_effect=query)
        plugin = storage_device.StorageDevicePlugin.__new__(storage_device.StorageDevicePlugin)
        luns = plugin.get_fc_luns(True)
        self.assertEqual(2, len(luns))
        self.assertEqual(['mpath', 'disk'], [lun.type for lun in luns])
        self.assertEqual(['209715200'] * 2, [lun.size for lun in luns])
        self.assertEqual(['36001', '36002'], [lun.wwids[0] for lun in luns])
        self.assertEqual(4, len(commands), 'four snapshots must replace per-path commands')
        running.assert_called_once_with()
        check.assert_called_once_with('multipath -c /dev/sdb')
        scsi.assert_called_once_with()

    def test_rescan_preserves_existing_target_selection_without_duplicate_records(self):
        self.patch(storage_device.bash, 'bash_o', return_value='1:0:1\n1:0:10\n')
        first = '[1:0:1:0] disk TEST /dev/sda 36001'
        second = '[1:0:10:0] disk TEST /dev/sdb 36002'
        self.patch(lvm, 'run_lsscsi_i', return_value=[first, second])
        self.patch(storage_device.linux, 'write_file')
        for name in ['get_lsblk_infos', 'get_device_paths', 'get_storage_wwnns']:
            self.patch(lvm, name, return_value={})
        self.patch(lvm, 'is_multipath_running', return_value=False)
        topology = self.patch(lvm, 'get_multipath_slaves')
        plugin = storage_device.StorageDevicePlugin.__new__(storage_device.StorageDevicePlugin)
        self.patch(plugin, 'get_fc_device_info', side_effect=lambda info, *args: info)
        self.assertEqual([first, second, second], plugin.get_fc_luns(True),
                         'rescan must not amplify records selected by the existing target matching')
        topology.assert_not_called()

    def test_cached_device_results_do_not_modify_other_results_or_snapshot(self):
        snapshot = lvm.StorageDeviceScanSnapshot()
        snapshot.blk_infos = {'sda': lvm._parse_lsblk_info(self.block('sda'))}
        snapshot.device_paths = {'sda': 'fc-a'}
        first = lvm.get_device_info('sda', {'sda': 'first-wwid'}, snapshot)
        first.type = 'mpath'
        second = lvm.get_device_info('sda', {'sda': 'second-wwid'}, snapshot)
        self.assertEqual('first-wwid', first.wwid)
        self.assertEqual('second-wwid', second.wwid)
        self.assertEqual('disk', second.type)
        self.assertIsNone(snapshot.blk_infos['sda'].wwid)
        self.assertIsNone(snapshot.blk_infos['sda'].path)
        self.assertEqual('disk', snapshot.blk_infos['sda'].type)

    def test_nvme_scan_reuses_existing_snapshots_and_preserves_identity(self):
        names = ['nvme0n1', 'nvme1n1']
        infos = {name: lvm._parse_lsblk_info(self.block(name)) for name in names}
        blocks = self.patch(lvm, 'get_lsblk_infos', return_value=infos)
        paths = self.patch(lvm, 'get_device_paths', return_value={'nvme0n1': 'nvme-path', 'nvme1n1': None})
        running = self.patch(lvm, 'is_multipath_running', return_value=True)
        topology = self.patch(lvm, 'get_multipath_slaves', return_value={'nvme0n1'})
        self.patch(storage_device.bash, 'bash_errorout', return_value=
                   '{"Devices":[{"DevicePath":"/dev/nvme0n1"},{"DevicePath":"/dev/nvme1n1"}]}')
        self.patch(lvm.bash, 'bash_roe', side_effect=AssertionError('unexpected per-device command'))
        check = self.patch(lvm.bash, 'bash_r', return_value=1)
        self.patch(lvm.shell, 'call', side_effect=AssertionError('unexpected per-device link query'))
        self.patch(storage_device.os.path, 'exists', return_value=False)
        self.patch(storage_device.linux, 'read_file', side_effect=
                   lambda path: 'nqn.test\n' if path.endswith('/subsysnqn') else 'tcp\n')
        plugin = storage_device.StorageDevicePlugin.__new__(storage_device.StorageDevicePlugin)
        luns = plugin.get_nvme_luns(False)
        self.assertEqual(['mpath', 'disk'], [lun.type for lun in luns])
        self.assertEqual(['nvme-path', '0x6001'], [lun.path for lun in luns])
        self.assertEqual([['0x6001'], ['0x6001']], [lun.wwids for lun in luns])
        self.assertEqual(['nqn.test', 'nqn.test'], [lun.nqn for lun in luns])
        self.assertEqual(['tcp', 'tcp'], [lun.transport for lun in luns])
        check.assert_called_once_with('multipath -c /dev/nvme1n1')
        for query in [blocks, paths, running, topology]:
            query.assert_called_once_with()

    def test_candidates_share_snapshots_across_mpath_disk_and_nvme(self):
        names = ['sda', 'sdb', 'nvme0n1']
        infos = {name: lvm._parse_lsblk_info(self.block(name)) for name in names}
        blocks = self.patch(lvm, 'get_lsblk_infos', return_value=infos)
        paths = self.patch(lvm, 'get_device_paths', return_value={name: 'path-' + name for name in names})
        nodes = self.patch(lvm, 'get_storage_wwnns', return_value={'1:0:1': '0x111'})
        self.patch(lvm, 'get_lsscsi_info', return_value={'sda': 'scsi-a', 'sdb': 'scsi-b'})
        self.patch(lvm, 'get_dev_iqn', return_value={})
        self.patch(lvm, 'get_nqn', return_value='nqn.test')
        self.patch(lvm, 'get_nvme_transport', return_value='tcp')
        self.patch(lvm, 'is_multipath_running', return_value=True)
        self.patch(lvm.os.path, 'exists', side_effect=lambda path:
                   path in ['/usr/sbin/nvme', '/sys/block/nvme0n1/wwid'])
        self.patch(lvm.os.path, 'realpath', side_effect=lambda path:
                   '/dev/dm-0' if path == '/dev/mapper/mpatha' else path)
        self.patch(lvm.os, 'listdir', return_value=['sda'])
        self.patch(lvm.linux, 'read_file', return_value='nvme-wwid\n')
        self.patch(lvm.linux, 'read_file_strip', return_value='mpath-scsi-a')

        def shell_cmd(command):
            result = mock.Mock(return_code=0)
            if command == 'multipath -l -v1':
                result.stdout = 'mpatha\n'
            elif command == 'nvme list -o json':
                result.stdout = '{"Devices":[{"DevicePath":"/dev/nvme0n1"}]}'
            else:
                self.fail('unexpected command: ' + command)
            return result

        def shell_call(command):
            if command.startswith('lsblk -e 43 '):
                return '/dev/sda\n/dev/sdb\n/dev/nvme0n1\n'
            if command.startswith('multipath -l |'):
                return 'sda\n'
            self.fail('unexpected per-device command: ' + command)

        self.patch(lvm.shell, 'ShellCmd', side_effect=shell_cmd)
        self.patch(lvm.shell, 'call', side_effect=shell_call)
        self.patch(lvm.bash, 'bash_roe', side_effect=AssertionError('unexpected per-device command'))
        wipefs = self.patch(lvm.bash, 'bash_r', return_value=0)
        devices = lvm.get_block_devices()
        self.assertEqual(['sda', 'sdb', 'nvme0n1'], [d.dev_name for d in devices])
        self.assertEqual(['mpath', 'lvm-pv', 'disk'], [d.type for d in devices])
        self.assertEqual(['scsi-a', 'scsi-b', 'nvme-wwid'], [d.wwid for d in devices])
        self.assertEqual(['0x111', '0x111', 'nqn.test'], [d.targetIdentifier for d in devices])
        self.assertEqual(['fc', 'fc', 'nvme'], [d.source for d in devices])
        self.assertEqual(['path-sda', 'path-sdb', 'path-nvme0n1'], [d.path for d in devices])
        self.assertEqual('fc', infos['nvme0n1'].source)
        self.assertEqual(['disk'] * 3, [infos[name].type for name in names])
        wipefs.assert_called_once_with('wipefs -n /dev/sdb | grep LVM2  > /dev/null')
        for query in [blocks, paths, nodes]:
            query.assert_called_once_with()

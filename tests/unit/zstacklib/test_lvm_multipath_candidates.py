import importlib.util
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def lvm():
    module_path = Path(__file__).resolve().parents[3] / 'zstacklib/zstacklib/utils/lvm.py'
    spec = importlib.util.spec_from_file_location('lvm_candidates_under_test', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def scan(lvm, monkeypatch):
    wwid = '360014056568000200004000800000000'
    state = SimpleNamespace(slaves=['sdf', 'sdd', 'sdb'], uuid='mpath-' + wwid, wwid=wwid)
    state.scsi_info = {'sdd': wwid, 'sdb': wwid}
    state.snapshot = lvm.StorageDeviceScanSnapshot()
    state.snapshot.blk_infos = {}
    state.snapshot.device_paths = {}
    for index, name in enumerate(state.slaves):
        row = ('NAME="/dev/%s" VENDOR="LIO-ORG" MODEL="FILEIO" WWN="0x6001" SERIAL="test-lun" '
               'HCTL="%d:0:0:1" TYPE="disk" SIZE="2147483648" TRAN="iscsi"') % (name, index + 3)
        state.snapshot.blk_infos[name] = lvm._parse_lsblk_info(row)
        state.snapshot.device_paths[name] = 'iscsi-path-' + name

    def command(cmd):
        assert cmd == 'multipath -l -v1'
        return Mock(return_code=0, stdout='mpathc\n')

    def read_uuid(path):
        assert path == '/sys/class/block/dm-4/dm/uuid'
        return state.uuid

    def start_thread(target, args):
        worker = threading.Thread(target=target, args=args)
        worker.start()
        return worker

    realpath = lvm.os.path.realpath
    listdir = lvm.os.listdir
    monkeypatch.setattr(lvm.shell, 'ShellCmd', command)
    monkeypatch.setattr(lvm.os.path, 'realpath', lambda path: (
        '/dev/dm-4' if path == '/dev/mapper/mpathc' else realpath(path)))
    monkeypatch.setattr(lvm.os, 'listdir', lambda path: (
        list(state.slaves) if path == '/sys/class/block/dm-4/slaves/' else listdir(path)))
    monkeypatch.setattr(lvm.linux, 'read_file_strip', read_uuid)
    monkeypatch.setattr(lvm.thread.ThreadFacade, 'run_in_thread', start_thread)
    monkeypatch.setattr(lvm.bash, 'bash_roe', lambda *args: (1, '', 'device unavailable'))
    state.scan = lambda: lvm.get_mpath_block_devices(state.scsi_info, state.snapshot)
    return state


def test_failed_first_path_uses_healthy_path_metadata(lvm, scan):
    devices, slaves = scan.scan()

    assert slaves == ['sdf', 'sdd', 'sdb']
    assert len(devices) == 1
    device = devices[0]
    assert (device.wwid, device.dev_name, device.name) == (scan.wwid, 'sdd', '/dev/sdd')
    assert (device.path, device.source, device.type) == ('iscsi-path-sdd', 'iscsi', 'mpath')
    assert (device.vendor, device.model, device.size, device.hctl) == ('LIO-ORG', 'FILEIO', '2147483648', '4:0:0:1')
    assert scan.snapshot.blk_infos['sdd'].type == 'disk'
    assert scan.snapshot.blk_infos['sdd'].wwid is None


def test_healthy_first_path_keeps_existing_selection(lvm, scan, monkeypatch):
    scan.scsi_info['sdf'] = scan.wwid
    probe = Mock(wraps=lvm.get_device_info)
    monkeypatch.setattr(lvm, 'get_device_info', probe)

    devices, _ = scan.scan()

    assert devices[0].dev_name == 'sdf'
    probe.assert_called_once_with('sdf', scan.scsi_info, scan.snapshot)


def test_missing_first_path_metadata_does_not_hide_healthy_paths(scan):
    scan.scsi_info['sdf'] = scan.wwid
    del scan.snapshot.blk_infos['sdf']

    devices, _ = scan.scan()

    assert [d.dev_name for d in devices] == ['sdd']


def test_path_probe_exception_does_not_hide_healthy_paths(lvm, scan, monkeypatch):
    get_device_info = lvm.get_device_info

    def probe(name, scsi_info, snapshot):
        if name == 'sdf':
            raise OSError('path disappeared during scan')
        return get_device_info(name, scsi_info, snapshot)

    monkeypatch.setattr(lvm, 'get_device_info', probe)

    devices, _ = scan.scan()

    assert [d.dev_name for d in devices] == ['sdd']


def test_all_failed_paths_stay_excluded_from_single_disk_scan(scan):
    scan.scsi_info.clear()

    devices, slaves = scan.scan()

    assert devices == []
    assert slaves == ['sdf', 'sdd', 'sdb']


def test_mismatched_path_identity_is_not_used_for_map(scan):
    scan.scsi_info['sdf'] = 'another-lun'

    devices, _ = scan.scan()

    assert [(d.wwid, d.dev_name) for d in devices] == [(scan.wwid, 'sdd')]


@pytest.mark.parametrize('uuid', [None, '', 'LVM-unrelated', 'mpath-'])
def test_unverified_map_identity_is_not_reported(scan, uuid):
    scan.uuid = uuid
    scan.scsi_info['sdf'] = scan.wwid

    devices, slaves = scan.scan()

    assert devices == []
    assert slaves == ['sdf', 'sdd', 'sdb']


def test_map_wwid_with_hyphens_is_not_truncated(scan):
    scan.wwid = 'vendor-lun-123'
    scan.uuid = 'mpath-' + scan.wwid
    scan.scsi_info = {'sdd': scan.wwid, 'sdb': scan.wwid}

    devices, _ = scan.scan()

    assert [d.wwid for d in devices] == [scan.wwid]


def test_no_slave_map_preserves_existing_placeholder(lvm, scan, monkeypatch):
    scan.slaves = []
    monkeypatch.setattr(lvm, 'get_dm_wwid', lambda dm: scan.wwid)

    devices, slaves = scan.scan()

    assert slaves == []
    assert len(devices) == 1
    assert (devices[0].wwid, devices[0].type) == (scan.wwid, 'mpath')
    assert devices[0].name is None


def test_candidate_iqn_follows_selected_path_and_all_slaves_remain_excluded(lvm, scan, monkeypatch):
    monkeypatch.setattr(lvm, 'get_lsscsi_info', lambda: scan.scsi_info)
    monkeypatch.setattr(lvm, 'get_lsblk_infos', lambda: scan.snapshot.blk_infos)
    monkeypatch.setattr(lvm, 'get_device_paths', lambda: scan.snapshot.device_paths)
    monkeypatch.setattr(lvm, 'get_storage_wwnns', lambda: {})
    disks = Mock(return_value=[])
    monkeypatch.setattr(lvm, 'get_disk_block_devices', disks)
    monkeypatch.setattr(lvm, 'get_nvme_block_devices', lambda snapshot: [])
    monkeypatch.setattr(lvm, 'get_dev_iqn', lambda: {'sdf': 'stale-target', 'sdd': 'iqn.correct-target'})

    devices = lvm.get_block_devices()

    assert len(devices) == 1
    assert devices[0].targetIdentifier == 'iqn.correct-target'
    assert disks.call_args.args[0] == ['sdf', 'sdd', 'sdb']
    assert disks.call_args.args[2].blk_infos is scan.snapshot.blk_infos
